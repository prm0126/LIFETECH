"""
Custom-report execution: validates user SQL (read-only) and shapes results
into card / table / bar / line payloads for the dashboard.

Safety: only a single SELECT (or WITH ... SELECT) statement is allowed, no
semicolons, no DML/DDL/PLSQL keywords, and rows are capped. For defense in
depth, run the app with a read-only Oracle account (see README).
"""
import datetime
import re
from decimal import Decimal

from config import Config
import db

VALID_TYPES = ("card", "table", "bar", "line")

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|"
    r"begin|declare|call|exec|execute|commit|rollback|savepoint|lock)\b", re.I)


def clean_sql(sql):
    s = (sql or "").strip()
    while s.endswith(";"):
        s = s[:-1].strip()
    if not s:
        raise ValueError("SQL is empty.")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("Only SELECT (or WITH ... SELECT) queries are allowed.")
    if ";" in s:
        raise ValueError("Only a single statement is allowed (remove the ';').")
    if _FORBIDDEN.search(s):
        raise ValueError("Only read-only SELECT queries are allowed.")
    return s


def _coerce(v):
    """Make a DB value JSON-serialisable."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, datetime.date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (bytes, bytearray)):
        return "<binary>"
    return v


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_select(sql, limit=None):
    limit = limit or Config.CUSTOM_MAX_ROWS
    s = clean_sql(sql)
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(s)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchmany(limit)
    return cols, [[_coerce(v) for v in r] for r in rows]


def shape(qtype, cols, rows):
    if qtype == "card":
        value = rows[0][0] if rows and rows[0] else 0
        return {"type": "card", "value": value, "label": cols[0] if cols else ""}

    if qtype == "bar":
        return {
            "type": "bar",
            "labels": [str(r[0]) for r in rows],
            "values": [_num(r[1]) if len(r) > 1 else 0 for r in rows],
        }

    if qtype == "line":
        # 3+ columns -> (label, series, value) multi-series; else single series
        if cols and len(cols) >= 3:
            labels = sorted({str(r[0]) for r in rows})
            idx = {l: i for i, l in enumerate(labels)}
            grids = {}
            for r in rows:
                name = str(r[1])
                grids.setdefault(name, [0] * len(labels))[idx[str(r[0])]] += _num(r[2])
            return {"type": "line", "labels": labels,
                    "series": [{"name": n, "values": grids[n]} for n in grids]}
        return {
            "type": "line",
            "labels": [str(r[0]) for r in rows],
            "series": [{"name": cols[1] if len(cols) > 1 else "value",
                        "values": [_num(r[1]) if len(r) > 1 else 0 for r in rows]}],
        }

    return {"type": "table", "columns": cols, "rows": rows}


def run_saved(item):
    cols, rows = run_select(item["sql"])
    data = shape(item["type"], cols, rows)
    data["id"] = item["id"]
    data["title"] = item["title"]
    return data
