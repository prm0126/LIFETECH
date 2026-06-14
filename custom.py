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

# Interactive parameters a report's SQL may reference as bind variables.
#   :date_from / :date_to  -> date range (DATE binds)
#   :gran                  -> TRUNC granularity: 'DD','IW','MM','YYYY'
SUPPORTED_PARAMS = ("date_from", "date_to", "gran")
_GRAN = {"DD", "IW", "MM", "YYYY"}
_BIND_RE = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")


def required_params(sql):
    found = {m.group(1).lower() for m in _BIND_RE.finditer(sql or "")}
    return [p for p in SUPPORTED_PARAMS if p in found]


def validate_params(sql):
    """Reject binds that the dashboard cannot supply values for."""
    found = {m.group(1).lower() for m in _BIND_RE.finditer(sql or "")}
    extra = found - set(SUPPORTED_PARAMS)
    if extra:
        raise ValueError(
            "Unknown parameter(s): " + ", ".join(":" + e for e in sorted(extra)) +
            ". Allowed interactive parameters are :date_from, :date_to, :gran.")


def _parse_date(value, default):
    if not value:
        return default
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return default


def build_binds(sql, raw):
    """Bind dict for whichever supported params appear in the SQL."""
    raw = raw or {}
    today = datetime.date.today()
    binds = {}
    for p in required_params(sql):
        if p == "gran":
            g = str(raw.get("gran") or "DD").upper()
            binds["gran"] = g if g in _GRAN else "DD"
        elif p == "date_from":
            binds["date_from"] = _parse_date(raw.get("date_from"), today - datetime.timedelta(days=30))
        elif p == "date_to":
            binds["date_to"] = _parse_date(raw.get("date_to"), today)
    return binds

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


def _is_number(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _value_hint(cols, raw_values):
    """Return a friendly warning when a chart's value column won't plot."""
    if not raw_values:
        return None
    if len(cols) > 2:
        return ("Only the first 2 columns are used here (label, value). Your query "
                "returned {} columns — for a per-series trend choose a Line chart "
                "instead.".format(len(cols)))
    if all(not _is_number(v) for v in raw_values):
        return ("The value column isn't a number, so everything is 0. Put a numeric "
                "column (e.g. COUNT(*)) as the 2nd column.")
    return None


def run_select(sql, limit=None, binds=None):
    limit = limit or Config.CUSTOM_MAX_ROWS
    s = clean_sql(sql)
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(s, binds or {})
            cols = [c[0] for c in cur.description]
            rows = cur.fetchmany(limit)
    return cols, [[_coerce(v) for v in r] for r in rows]


def shape(qtype, cols, rows):
    if qtype == "card":
        value = rows[0][0] if rows and rows[0] else 0
        return {"type": "card", "value": value, "label": cols[0] if cols else ""}

    if qtype == "bar":
        raw = [r[1] if len(r) > 1 else None for r in rows]
        out = {"type": "bar", "labels": [str(r[0]) for r in rows],
               "values": [_num(v) for v in raw]}
        note = _value_hint(cols, raw)
        if note:
            out["note"] = note
        return out

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
        raw = [r[1] if len(r) > 1 else None for r in rows]
        out = {"type": "line", "labels": [str(r[0]) for r in rows],
               "series": [{"name": cols[1] if len(cols) > 1 else "value",
                           "values": [_num(v) for v in raw]}]}
        note = _value_hint(cols, raw)
        if note:
            out["note"] = note
        return out

    return {"type": "table", "columns": cols, "rows": rows}


def run_saved(item, raw_params=None):
    binds = build_binds(item["sql"], raw_params)
    cols, rows = run_select(item["sql"], binds=binds)
    data = shape(item["type"], cols, rows)
    data["id"] = item["id"]
    data["title"] = item["title"]
    data["params"] = required_params(item["sql"])
    return data
