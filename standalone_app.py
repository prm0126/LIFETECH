"""
Oracle Filter & Update tool  -  SINGLE-FILE version.

Everything (HTML, CSS, JavaScript and the Python server) is bundled into this
one file so it can be dropped into a folder and run with no other files.

What it does:
  1. Connect to an Oracle database (host / port / service / user / password).
  2. Pick a table and build one or more filter conditions.
  3. Preview the rows that match the filter.
  4. Update a single chosen column to 1 or 0 for every matching row.

How to run (Windows PowerShell):
    py -m pip install flask python-oracledb
    py app.py
Then open http://127.0.0.1:5000 in a browser.

python-oracledb runs in "thin" mode, so no Oracle client install is needed.
Filter *values* are always sent as bind variables. Table/column *names* are
validated against the table's real columns before being used in SQL.
"""

import re

import oracledb
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# A bare Oracle identifier: starts with a letter, then letters/digits/_ $ #.
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")

VALUE_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "NOT LIKE", "IN"}
NO_VALUE_OPERATORS = {"IS NULL", "IS NOT NULL"}
ALL_OPERATORS = VALUE_OPERATORS | NO_VALUE_OPERATORS

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
    """Turn the filter list into a WHERE clause plus a bind dict."""
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
    return Response(PAGE, mimetype="text/html")


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
            ok=True, columns=columns, rows=rows,
            total=total, shown=len(rows), limit=PREVIEW_LIMIT,
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


# --------------------------------------------------------------------------
# The whole front-end (HTML + CSS + JS) lives in this one string and is served
# at "/". It is NOT a Jinja template, so braces in the CSS/JS are left alone.
# --------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Oracle Filter &amp; Update</title>
<style>
:root{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#2563eb;--danger:#dc2626;--ok:#16a34a;}
*{box-sizing:border-box;}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text);}
header{padding:24px 32px 8px;}
header h1{margin:0;font-size:22px;}
header .sub{margin:4px 0 0;color:var(--muted);}
main{max-width:1000px;margin:0 auto;padding:16px 24px 64px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin:16px 0;}
.card h2{margin:0 0 14px;font-size:16px;display:flex;align-items:center;gap:10px;}
.step{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:var(--accent);color:#fff;font-size:13px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:14px;}
label{display:flex;flex-direction:column;font-size:13px;color:var(--muted);gap:4px;}
input,select{background:#0f172a;border:1px solid var(--border);color:var(--text);border-radius:6px;padding:8px 10px;font-size:14px;}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px;}
button{background:#334155;color:var(--text);border:none;border-radius:6px;padding:9px 16px;font-size:14px;cursor:pointer;margin-right:8px;}
button:hover{filter:brightness(1.12);}
button.primary{background:var(--accent);color:#fff;}
button.danger{background:var(--danger);color:#fff;}
button:disabled{opacity:.5;cursor:not-allowed;}
.status{font-size:13px;margin-left:6px;}
.status.ok{color:var(--ok);}
.status.err{color:#f87171;}
.match-row{margin-bottom:12px;color:var(--muted);font-size:14px;}
.match-row select{display:inline-block;width:auto;margin:0 4px;}
.filter-row{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:center;}
.filter-row .remove{background:transparent;color:#f87171;font-size:18px;padding:4px 10px;}
.table-wrap{overflow-x:auto;max-height:420px;overflow-y:auto;}
table{border-collapse:collapse;width:100%;font-size:13px;}
th,td{border:1px solid var(--border);padding:6px 9px;text-align:left;white-space:nowrap;}
th{background:#0f172a;position:sticky;top:0;}
.summary{color:var(--muted);font-size:14px;}
.warn{color:#fbbf24;font-size:14px;}
</style>
</head>
<body>
<header>
  <h1>Oracle Filter &amp; Update</h1>
  <p class="sub">Connect &rarr; filter rows &rarr; set one column to 1 or 0.</p>
</header>
<main>
  <section class="card">
    <h2><span class="step">1</span> Connection</h2>
    <div class="grid">
      <label>Host <input id="host" placeholder="db.example.com" /></label>
      <label>Port <input id="port" value="1521" /></label>
      <label>Service name <input id="service_name" placeholder="ORCLPDB1" /></label>
      <label>User <input id="user" placeholder="scott" /></label>
      <label>Password <input id="password" type="password" /></label>
    </div>
    <button id="connectBtn" class="primary">Connect</button>
    <span id="connStatus" class="status"></span>
  </section>

  <section class="card" id="tableCard" hidden>
    <h2><span class="step">2</span> Table</h2>
    <label>Table <select id="tableSelect"></select></label>
    <button id="loadColumnsBtn">Load columns</button>
    <span id="tableStatus" class="status"></span>
  </section>

  <section class="card" id="filterCard" hidden>
    <h2><span class="step">3</span> Filter conditions</h2>
    <div class="match-row">Match
      <select id="matchSelect">
        <option value="AND">ALL (AND)</option>
        <option value="OR">ANY (OR)</option>
      </select> of the conditions below.</div>
    <div id="filters"></div>
    <button id="addFilterBtn">+ Add condition</button>
    <button id="previewBtn" class="primary">Preview matching rows</button>
    <span id="previewStatus" class="status"></span>
  </section>

  <section class="card" id="previewCard" hidden>
    <h2>Matching rows</h2>
    <p id="previewSummary" class="summary"></p>
    <div class="table-wrap"><table id="previewTable"></table></div>
  </section>

  <section class="card" id="updateCard" hidden>
    <h2><span class="step">4</span> Update a column</h2>
    <div class="grid">
      <label>Column to update <select id="targetColumn"></select></label>
      <label>Set value to
        <select id="newValue"><option value="1">1</option><option value="0">0</option></select>
      </label>
    </div>
    <p class="warn">This updates the chosen column for <b id="updateCount">all matching</b> rows and commits.</p>
    <button id="updateBtn" class="danger">Apply update</button>
    <span id="updateStatus" class="status"></span>
  </section>
</main>
<script>
"use strict";
const state={columns:[]};
const OPERATORS=["=","!=","<",">","<=",">=","LIKE","NOT LIKE","IN","IS NULL","IS NOT NULL"];
const NO_VALUE_OPS=new Set(["IS NULL","IS NOT NULL"]);
function $(id){return document.getElementById(id);}
function connectionParams(){return{host:$("host").value,port:$("port").value,service_name:$("service_name").value,user:$("user").value,password:$("password").value};}
function setStatus(el,msg,ok){el.textContent=msg;el.className="status "+(ok?"ok":"err");}
async function postJSON(url,body){
  const res=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const data=await res.json();
  if(!res.ok||!data.ok){throw new Error(data.error||("Request failed ("+res.status+")"));}
  return data;
}
function collectFilters(){
  const rows=document.querySelectorAll(".filter-row");const filters=[];
  rows.forEach((row)=>{
    const column=row.querySelector(".f-col").value;
    const operator=row.querySelector(".f-op").value;
    const valueEl=row.querySelector(".f-val");
    const value=valueEl?valueEl.value:"";
    if(column)filters.push({column,operator,value});
  });
  return filters;
}
function basePayload(){return{connection:connectionParams(),table:$("tableSelect").value,filters:collectFilters(),match:$("matchSelect").value};}
function columnOptions(){return state.columns.map((c)=>"<option value=\""+c+"\">"+c+"</option>").join("");}
function addFilterRow(){
  const row=document.createElement("div");row.className="filter-row";
  row.innerHTML="<select class=\"f-col\">"+columnOptions()+"</select>"+
    "<select class=\"f-op\">"+OPERATORS.map((o)=>"<option>"+o+"</option>").join("")+"</select>"+
    "<input class=\"f-val\" placeholder=\"value\" />"+
    "<button class=\"remove\" title=\"Remove\">&times;</button>";
  const op=row.querySelector(".f-op");const val=row.querySelector(".f-val");
  op.addEventListener("change",()=>{val.style.visibility=NO_VALUE_OPS.has(op.value)?"hidden":"visible";});
  row.querySelector(".remove").addEventListener("click",()=>row.remove());
  $("filters").appendChild(row);
}
function escapeHtml(s){return String(s).replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));}
function renderPreview(data){
  const summary=data.shown<data.total?("Showing first "+data.shown+" of "+data.total+" matching rows."):(data.total+" matching row(s).");
  $("previewSummary").textContent=summary;
  $("updateCount").textContent=data.total+" matching";
  const head="<tr>"+data.columns.map((c)=>"<th>"+c+"</th>").join("")+"</tr>";
  const body=data.rows.map((r)=>"<tr>"+r.map((v)=>"<td>"+escapeHtml(v)+"</td>").join("")+"</tr>").join("");
  $("previewTable").innerHTML=head+body;
  $("previewCard").hidden=false;
}
$("connectBtn").addEventListener("click",async()=>{
  const btn=$("connectBtn");btn.disabled=true;setStatus($("connStatus"),"Connecting...",true);
  try{
    const data=await postJSON("/api/connect",{connection:connectionParams()});
    $("tableSelect").innerHTML=data.tables.map((t)=>"<option>"+t+"</option>").join("");
    $("tableCard").hidden=false;
    setStatus($("connStatus"),"Connected. "+data.tables.length+" table(s) found.",true);
  }catch(e){setStatus($("connStatus"),e.message,false);}finally{btn.disabled=false;}
});
$("loadColumnsBtn").addEventListener("click",async()=>{
  setStatus($("tableStatus"),"Loading columns...",true);
  try{
    const data=await postJSON("/api/columns",{connection:connectionParams(),table:$("tableSelect").value});
    state.columns=data.columns;$("filters").innerHTML="";addFilterRow();
    $("targetColumn").innerHTML=columnOptions();
    $("filterCard").hidden=false;$("updateCard").hidden=false;
    setStatus($("tableStatus"),data.columns.length+" column(s) loaded.",true);
  }catch(e){setStatus($("tableStatus"),e.message,false);}
});
$("addFilterBtn").addEventListener("click",addFilterRow);
$("previewBtn").addEventListener("click",async()=>{
  setStatus($("previewStatus"),"Running...",true);
  try{const data=await postJSON("/api/preview",basePayload());renderPreview(data);setStatus($("previewStatus"),"Done.",true);}
  catch(e){setStatus($("previewStatus"),e.message,false);}
});
$("updateBtn").addEventListener("click",async()=>{
  const target=$("targetColumn").value;const value=$("newValue").value;
  if(!confirm("Set "+target+" = "+value+" for ALL matching rows and commit?"))return;
  setStatus($("updateStatus"),"Updating...",true);
  try{
    const payload=basePayload();payload.target_column=target;payload.new_value=parseInt(value,10);
    const data=await postJSON("/api/update",payload);
    setStatus($("updateStatus"),"Updated "+data.affected+" row(s): "+target+" = "+data.value+". Committed.",true);
  }catch(e){setStatus($("updateStatus"),e.message,false);}
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
