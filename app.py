"""
LIFETECH Oracle DB Explorer
---------------------------
A lightweight Flask web app to connect to an Oracle database, browse tables,
view and search column data, edit cells inline, and run conditional bulk
updates (e.g. set a flag column to 1 or 0 where a condition matches).

Configuration is read from environment variables (see .env.example).
"""

import os
import re

import oracledb
from flask import Flask, jsonify, request, render_template

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional at runtime
    pass

app = Flask(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
DB_USER = os.environ.get("ORACLE_USER", "")
DB_PASSWORD = os.environ.get("ORACLE_PASSWORD", "")
# DSN can be host:port/service_name or a tnsnames alias.
DB_DSN = os.environ.get("ORACLE_DSN", "localhost:1521/XEPDB1")
# Optional: schema to browse (defaults to the connected user's schema).
DB_SCHEMA = os.environ.get("ORACLE_SCHEMA", "").upper()
# Thick mode requires an Oracle client install; thin mode (default) does not.
ORACLE_THICK = os.environ.get("ORACLE_THICK", "false").lower() == "true"
PAGE_SIZE_MAX = 500

if ORACLE_THICK:
    lib_dir = os.environ.get("ORACLE_CLIENT_LIB_DIR") or None
    oracledb.init_oracle_client(lib_dir=lib_dir)

_pool = None


def get_pool():
    """Lazily create a connection pool so the app starts even without a DB."""
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=DB_DSN,
            min=1,
            max=4,
            increment=1,
        )
    return _pool


def current_schema(conn):
    return DB_SCHEMA or conn.username.upper()


# --------------------------------------------------------------------------
# Identifier validation (defence against SQL injection in object names)
# --------------------------------------------------------------------------
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


def valid_identifier(name):
    return bool(name) and bool(IDENTIFIER_RE.match(name))


def assert_table_exists(conn, table):
    """Raise ValueError unless `table` is a real table/view in the schema."""
    if not valid_identifier(table):
        raise ValueError("Invalid table name")
    schema = current_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM all_tables
             WHERE owner = :owner AND table_name = :tname
            UNION ALL
            SELECT COUNT(*) FROM all_views
             WHERE owner = :owner AND view_name = :tname
            """,
            owner=schema,
            tname=table.upper(),
        )
        total = sum(row[0] for row in cur.fetchall())
    if total == 0:
        raise ValueError(f"Table '{table}' not found in schema {schema}")
    return table.upper()


def get_columns(conn, table):
    """Return ordered column metadata for a validated table."""
    schema = current_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, nullable, data_length
              FROM all_tab_columns
             WHERE owner = :owner AND table_name = :tname
             ORDER BY column_id
            """,
            owner=schema,
            tname=table,
        )
        cols = [
            {
                "name": r[0],
                "type": r[1],
                "nullable": r[2] == "Y",
                "length": r[3],
            }
            for r in cur.fetchall()
        ]
    return cols


def column_names(conn, table):
    return {c["name"] for c in get_columns(conn, table)}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    """Surface non-secret connection info so the UI can show what it targets."""
    return jsonify(
        {
            "dsn": DB_DSN,
            "user": DB_USER,
            "schema": DB_SCHEMA or DB_USER.upper(),
            "configured": bool(DB_USER and DB_PASSWORD),
        }
    )


@app.route("/api/tables")
def api_tables():
    try:
        with get_pool().acquire() as conn:
            schema = current_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, 'TABLE' AS kind FROM all_tables
                     WHERE owner = :owner
                    UNION ALL
                    SELECT view_name, 'VIEW' FROM all_views
                     WHERE owner = :owner
                     ORDER BY 1
                    """,
                    owner=schema,
                )
                tables = [{"name": r[0], "kind": r[1]} for r in cur.fetchall()]
        return jsonify({"schema": schema, "tables": tables})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tables/<table>/columns")
def api_columns(table):
    try:
        with get_pool().acquire() as conn:
            table = assert_table_exists(conn, table)
            return jsonify({"table": table, "columns": get_columns(conn, table)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tables/<table>/data")
def api_data(table):
    """
    Paginated row data with optional per-column search filters.

    Query params:
      page      1-based page number
      page_size rows per page (capped at PAGE_SIZE_MAX)
      f_<COL>   case-insensitive substring filter for column COL
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(PAGE_SIZE_MAX, max(1, int(request.args.get("page_size", 50))))
        offset = (page - 1) * page_size

        with get_pool().acquire() as conn:
            table = assert_table_exists(conn, table)
            valid_cols = column_names(conn, table)

            # Build per-column filters with bind variables.
            where_parts = []
            binds = {}
            i = 0
            for key, value in request.args.items():
                if not key.startswith("f_") or value == "":
                    continue
                col = key[2:].upper()
                if col not in valid_cols:
                    continue
                bind_name = f"flt{i}"
                where_parts.append(
                    f'UPPER(TO_CHAR("{col}")) LIKE :{bind_name}'
                )
                binds[bind_name] = f"%{value.upper()}%"
                i += 1

            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT COUNT(*) FROM "{table}"{where_sql}', binds
                )
                total = cur.fetchone()[0]

            # ROWID gives every row a stable handle for inline updates.
            sql = (
                f'SELECT ROWIDTOCHAR(ROWID) AS "__ROWID__", t.* '
                f'FROM "{table}" t{where_sql} '
                f"ORDER BY ROWID "
                f"OFFSET :__off ROWS FETCH NEXT :__lim ROWS ONLY"
            )
            qbinds = dict(binds)
            qbinds["__off"] = offset
            qbinds["__lim"] = page_size

            with conn.cursor() as cur:
                cur.execute(sql, qbinds)
                col_names = [d[0] for d in cur.description]
                rows = []
                for record in cur.fetchall():
                    row = {}
                    for name, val in zip(col_names, record):
                        row[name] = _to_jsonable(val)
                    rows.append(row)

        return jsonify(
            {
                "table": table,
                "columns": [c for c in col_names if c != "__ROWID__"],
                "rows": rows,
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tables/<table>/cell", methods=["POST"])
def api_update_cell(table):
    """Update a single cell, identified by its ROWID."""
    try:
        payload = request.get_json(force=True)
        rowid = payload.get("rowid")
        column = (payload.get("column") or "").upper()
        value = payload.get("value")

        if not rowid:
            raise ValueError("Missing rowid")
        if not valid_identifier(column):
            raise ValueError("Invalid column name")

        with get_pool().acquire() as conn:
            table = assert_table_exists(conn, table)
            if column not in column_names(conn, table):
                raise ValueError(f"Column '{column}' not in table")

            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE "{table}" SET "{column}" = :val '
                    f"WHERE ROWID = CHARTOROWID(:rid)",
                    val=value,
                    rid=rowid,
                )
                affected = cur.rowcount
            conn.commit()
        return jsonify({"updated": affected})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tables/<table>/bulk-update", methods=["POST"])
def api_bulk_update(table):
    """
    Conditional bulk update: SET <column> = <value> WHERE <condition>.

    The condition is raw SQL supplied by the user (this is an admin tool),
    while the new value is always passed as a bind variable. A preview mode
    returns the affected row count without committing.
    """
    try:
        payload = request.get_json(force=True)
        column = (payload.get("column") or "").upper()
        value = payload.get("value")
        condition = (payload.get("condition") or "").strip()
        preview = bool(payload.get("preview", False))

        if not valid_identifier(column):
            raise ValueError("Invalid column name")
        if not condition:
            raise ValueError("A WHERE condition is required (use 1=1 to match all)")
        if ";" in condition:
            raise ValueError("Semicolons are not allowed in the condition")

        with get_pool().acquire() as conn:
            table = assert_table_exists(conn, table)
            if column not in column_names(conn, table):
                raise ValueError(f"Column '{column}' not in table")

            with conn.cursor() as cur:
                # Count matches first so the user knows the blast radius.
                cur.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE {condition}'
                )
                matched = cur.fetchone()[0]

                if preview:
                    return jsonify({"preview": True, "matched": matched})

                cur.execute(
                    f'UPDATE "{table}" SET "{column}" = :val WHERE {condition}',
                    val=value,
                )
                affected = cur.rowcount
            conn.commit()
        return jsonify({"updated": affected, "matched": matched})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


def _to_jsonable(val):
    """Convert Oracle types that aren't natively JSON-serialisable."""
    import datetime
    import decimal

    if val is None:
        return None
    if isinstance(val, decimal.Decimal):
        # Keep integers as ints, otherwise float.
        return int(val) if val == val.to_integral_value() else float(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat(sep=" ")
    if isinstance(val, oracledb.LOB):
        try:
            return val.read()
        except Exception:  # noqa: BLE001
            return "<LOB>"
    if isinstance(val, bytes):
        return val.hex()
    return val


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
