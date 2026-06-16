"use strict";

// Shared client state. Connection params + the loaded column list are reused
// across requests so the user only types them once.
const state = {
  columns: [],
};

const OPERATORS = [
  "=", "!=", "<", ">", "<=", ">=",
  "LIKE", "NOT LIKE", "IN", "IS NULL", "IS NOT NULL",
];
const NO_VALUE_OPS = new Set(["IS NULL", "IS NOT NULL"]);

function $(id) { return document.getElementById(id); }

function connectionParams() {
  return {
    host: $("host").value,
    port: $("port").value,
    service_name: $("service_name").value,
    user: $("user").value,
    password: $("password").value,
  };
}

function setStatus(el, msg, ok) {
  el.textContent = msg;
  el.className = "status " + (ok ? "ok" : "err");
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || ("Request failed (" + res.status + ")"));
  }
  return data;
}

// Collect the filter rows currently on screen into the API payload shape.
function collectFilters() {
  const rows = document.querySelectorAll(".filter-row");
  const filters = [];
  rows.forEach((row) => {
    const column = row.querySelector(".f-col").value;
    const operator = row.querySelector(".f-op").value;
    const valueEl = row.querySelector(".f-val");
    const value = valueEl ? valueEl.value : "";
    if (column) filters.push({ column, operator, value });
  });
  return filters;
}

function basePayload() {
  return {
    connection: connectionParams(),
    table: $("tableSelect").value,
    filters: collectFilters(),
    match: $("matchSelect").value,
  };
}

function columnOptions() {
  return state.columns.map((c) => `<option value="${c}">${c}</option>`).join("");
}

function addFilterRow() {
  const row = document.createElement("div");
  row.className = "filter-row";
  row.innerHTML = `
    <select class="f-col">${columnOptions()}</select>
    <select class="f-op">${OPERATORS.map((o) => `<option>${o}</option>`).join("")}</select>
    <input class="f-val" placeholder="value" />
    <button class="remove" title="Remove">&times;</button>
  `;
  // Hide the value box for IS NULL / IS NOT NULL.
  const op = row.querySelector(".f-op");
  const val = row.querySelector(".f-val");
  op.addEventListener("change", () => {
    val.style.visibility = NO_VALUE_OPS.has(op.value) ? "hidden" : "visible";
  });
  row.querySelector(".remove").addEventListener("click", () => row.remove());
  $("filters").appendChild(row);
}

function renderPreview(data) {
  const summary = data.shown < data.total
    ? `Showing first ${data.shown} of ${data.total} matching rows.`
    : `${data.total} matching row(s).`;
  $("previewSummary").textContent = summary;
  $("updateCount").textContent = `${data.total} matching`;

  const head = "<tr>" + data.columns.map((c) => `<th>${c}</th>`).join("") + "</tr>";
  const body = data.rows.map((r) =>
    "<tr>" + r.map((v) => `<td>${escapeHtml(v)}</td>`).join("") + "</tr>"
  ).join("");
  $("previewTable").innerHTML = head + body;
  $("previewCard").hidden = false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// --- wire up buttons ---

$("connectBtn").addEventListener("click", async () => {
  const btn = $("connectBtn");
  btn.disabled = true;
  setStatus($("connStatus"), "Connecting…", true);
  try {
    const data = await postJSON("/api/connect", { connection: connectionParams() });
    $("tableSelect").innerHTML = data.tables
      .map((t) => `<option>${t}</option>`).join("");
    $("tableCard").hidden = false;
    setStatus($("connStatus"), `Connected. ${data.tables.length} table(s) found.`, true);
  } catch (e) {
    setStatus($("connStatus"), e.message, false);
  } finally {
    btn.disabled = false;
  }
});

$("loadColumnsBtn").addEventListener("click", async () => {
  setStatus($("tableStatus"), "Loading columns…", true);
  try {
    const data = await postJSON("/api/columns", {
      connection: connectionParams(),
      table: $("tableSelect").value,
    });
    state.columns = data.columns;
    $("filters").innerHTML = "";
    addFilterRow();
    $("targetColumn").innerHTML = columnOptions();
    $("filterCard").hidden = false;
    $("updateCard").hidden = false;
    setStatus($("tableStatus"), `${data.columns.length} column(s) loaded.`, true);
  } catch (e) {
    setStatus($("tableStatus"), e.message, false);
  }
});

$("addFilterBtn").addEventListener("click", addFilterRow);

$("previewBtn").addEventListener("click", async () => {
  setStatus($("previewStatus"), "Running…", true);
  try {
    const data = await postJSON("/api/preview", basePayload());
    renderPreview(data);
    setStatus($("previewStatus"), "Done.", true);
  } catch (e) {
    setStatus($("previewStatus"), e.message, false);
  }
});

$("updateBtn").addEventListener("click", async () => {
  const target = $("targetColumn").value;
  const value = $("newValue").value;
  if (!confirm(`Set ${target} = ${value} for ALL matching rows and commit?`)) return;

  setStatus($("updateStatus"), "Updating…", true);
  try {
    const payload = basePayload();
    payload.target_column = target;
    payload.new_value = parseInt(value, 10);
    const data = await postJSON("/api/update", payload);
    setStatus($("updateStatus"),
      `Updated ${data.affected} row(s): ${target} = ${data.value}. Committed.`, true);
  } catch (e) {
    setStatus($("updateStatus"), e.message, false);
  }
});
