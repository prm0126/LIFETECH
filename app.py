"""
Oracle Filter & Update tool.

A small Flask web app that lets you:
  1. Connect to an Oracle database (host / port / service / user / password).
  2. Pick a table and build one or more filter conditions.
  3. Preview the rows that match the filter.
  4. Update a single chosen column to 1 or 0 for every matching row.

Connection details are kept on the client and sent with each request, so the
server stays stateless. Filter *values* are always sent as bind variables.
Table and column *names* cannot be bound, so they are validated against a
strict identifier pattern (and, for columns, against the table's real
columns) before being placed into SQL.
"""

import re

import oracledb
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# A bare Oracle identifier: starts with a letter, then letters/digits/_ $ #.
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")

# Operators that take a value vs. the ones that don't.
VALUE_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "NOT LIKE", "IN"}
NO_VALUE_OPERATORS = {"IS NULL", "IS NOT NULL"}
ALL_OPERATORS = VALUE_OPERATORS | NO_VALUE_OPERATORS

# Cap preview output so a stray filter can't try to stream a whole table.
PREVIEW_LIMIT = 200


class RequestError(Exception):
    """Raised for bad client input; surfaced to the UI as a 400."""


def valid_identifier(name):
    return isinstance(name, str) and bool(IDENTIFIER_RE.match(name))


def get_connection(conn_params):
    """Open a python-oracledb thin-mode connection from a params dict."""
    required = ("host", "port", "service_name", "user", "password")
    missing = [k for k in required if not str(conn_params.get(k, "")).strip()]
    if missing:
        raise RequestError("Missing connection field(s): " + ", ".join(missing))

    dsn = "{host}:{port}/{service}".format(
        host=conn_params["host"].strip(),
        port=str(conn_params["port"]).strip(),
        service=conn_params["service_name"].strip(),
    )
    try:
        return oracledb.connect(
            user=conn_params["user"].strip(),
            password=conn_params["password"],
            dsn=dsn,
        )
    except OSError as e:
        # DNS / socket failures (e.g. unknown host) aren't oracledb.Error,
        # so translate them into a clean, client-facing error.
        raise RequestError("Could not reach the database: {}".format(e))


def table_columns(conn, table):
    """Return the uppercase column names that actually exist on `table`."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM all_tab_columns "
            "WHERE table_name = :t ORDER BY column_id",
            t=table.upper(),
        )
        return [row[0] for row in cur.fetchall()]


def build_where(filters, match, valid_columns):
    """Turn the filter list into a WHERE clause plus a bind dict.

    `match` is "AND" or "OR". `valid_columns` is the set of real column names
    (uppercased) used to reject unknown columns.
    """
    if not filters:
        return "", {}

    match = (match or "AND").upper()
    if match not in ("AND", "OR"):
        raise RequestError("Match must be AND or OR.")

    clauses = []
    binds = {}
    for i, f in enumerate(filters):
        column = f.get("column", "")
        operator = (f.get("operator") or "").upper()

        if not valid_identifier(column) or column.upper() not in valid_columns:
            raise RequestError("Unknown or invalid column: {!r}".format(column))
        if operator not in ALL_OPERATORS:
            raise RequestError("Unsupported operator: {!r}".format(operator))

        if operator in NO_VALUE_OPERATORS:
            clauses.append("{col} {op}".format(col=column, op=operator))
            continue

        value = f.get("value", "")
        if operator == "IN":
            items = [v.strip() for v in str(value).split(",") if v.strip()]
            if not items:
                raise RequestError("IN filter needs at least one value.")
            names = []
            for j, item in enumerate(items):
                key = "b_{}_{}".format(i, j)
                binds[key] = item
                names.append(":" + key)
            clauses.append("{col} IN ({vals})".format(col=column, vals=", ".join(names)))
        else:
            key = "b_{}".format(i)
            binds[key] = value
            clauses.append("{col} {op} :{key}".format(col=column, op=operator, key=key))

    glue = " {} ".format(match)
    return "WHERE " + glue.join(clauses), binds


def parse_request():
    """Pull and lightly validate the common payload shared by endpoints."""
    data = request.get_json(silent=True) or {}
    conn_params = data.get("connection") or {}
    table = data.get("table") or ""
    if not valid_identifier(table):
        raise RequestError("Invalid or missing table name.")
    filters = data.get("filters") or []
    match = data.get("match", "AND")
    return data, conn_params, table, filters, match


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/connect", methods=["POST"])
def api_connect():
    """Test the connection and return the user's tables for the picker."""
    data = request.get_json(silent=True) or {}
    conn_params = data.get("connection") or {}
    try:
        conn = get_connection(conn_params)
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400
    except oracledb.Error as e:
        return jsonify(ok=False, error=str(e)), 400

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            tables = [row[0] for row in cur.fetchall()]
        return jsonify(ok=True, tables=tables)
    finally:
        conn.close()


@app.route("/api/columns", methods=["POST"])
def api_columns():
    """Return the columns for a chosen table."""
    try:
        _, conn_params, table, _, _ = parse_request()
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400
    try:
        conn = get_connection(conn_params)
    except (RequestError, oracledb.Error) as e:
        return jsonify(ok=False, error=str(e)), 400
    try:
        cols = table_columns(conn, table)
        if not cols:
            return jsonify(ok=False, error="Table not found or has no columns."), 400
        return jsonify(ok=True, columns=cols)
    finally:
        conn.close()


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Run a SELECT with the built filter and return up to PREVIEW_LIMIT rows."""
    try:
        _, conn_params, table, filters, match = parse_request()
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400
    try:
        conn = get_connection(conn_params)
    except (RequestError, oracledb.Error) as e:
        return jsonify(ok=False, error=str(e)), 400
    try:
        valid_cols = set(table_columns(conn, table))
        if not valid_cols:
            return jsonify(ok=False, error="Table not found."), 400
        where, binds = build_where(filters, match, valid_cols)

        count_sql = "SELECT COUNT(*) FROM {tbl} {where}".format(tbl=table, where=where)
        rows_sql = (
            "SELECT * FROM {tbl} {where} "
            "FETCH FIRST {lim} ROWS ONLY".format(tbl=table, where=where, lim=PREVIEW_LIMIT)
        )
        with conn.cursor() as cur:
            cur.execute(count_sql, binds)
            total = cur.fetchone()[0]

            cur.execute(rows_sql, binds)
            columns = [d[0] for d in cur.description]
            rows = [
                ["" if v is None else str(v) for v in row]
                for row in cur.fetchall()
            ]
        return jsonify(
            ok=True,
            columns=columns,
            rows=rows,
            total=total,
            shown=len(rows),
            limit=PREVIEW_LIMIT,
        )
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400
    except oracledb.Error as e:
        return jsonify(ok=False, error=str(e)), 400
    finally:
        conn.close()


@app.route("/api/update", methods=["POST"])
def api_update():
    """Set `target_column` to 0 or 1 for every row matching the filter."""
    try:
        data, conn_params, table, filters, match = parse_request()
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400

    target = data.get("target_column", "")
    new_value = data.get("new_value")
    if not valid_identifier(target):
        return jsonify(ok=False, error="Invalid target column."), 400
    if new_value not in (0, 1, "0", "1"):
        return jsonify(ok=False, error="New value must be 0 or 1."), 400
    new_value = int(new_value)

    try:
        conn = get_connection(conn_params)
    except (RequestError, oracledb.Error) as e:
        return jsonify(ok=False, error=str(e)), 400
    try:
        valid_cols = set(table_columns(conn, table))
        if target.upper() not in valid_cols:
            return jsonify(ok=False, error="Target column not found on table."), 400
        where, binds = build_where(filters, match, valid_cols)

        sql = "UPDATE {tbl} SET {col} = :new_val {where}".format(
            tbl=table, col=target, where=where
        )
        binds = dict(binds)
        binds["new_val"] = new_value
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            affected = cur.rowcount
        conn.commit()
        return jsonify(ok=True, affected=affected, value=new_value)
    except RequestError as e:
        return jsonify(ok=False, error=str(e)), 400
    except oracledb.Error as e:
        conn.rollback()
        return jsonify(ok=False, error=str(e)), 400
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
