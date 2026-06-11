"use strict";

const state = {
  table: null,
  columns: [],
  filters: {},
  page: 1,
  pageSize: 50,
  total: 0,
  bulkPreviewOk: false,
};

// ---------------------------------------------------------------- helpers
async function api(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, kind = "ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast " + kind;
  setTimeout(() => el.classList.add("hidden"), 3000);
}

function debounce(fn, ms) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

// ---------------------------------------------------------------- config
async function loadConfig() {
  try {
    const c = await api("/api/config");
    document.getElementById("connInfo").textContent =
      `${c.user || "?"}@${c.dsn}  ·  schema ${c.schema}` +
      (c.configured ? "" : "  (not configured)");
  } catch (e) {
    document.getElementById("connInfo").textContent = "config error";
  }
}

// ---------------------------------------------------------------- tables
async function loadTables() {
  const list = document.getElementById("tableList");
  list.innerHTML = "<li>Loading…</li>";
  try {
    const data = await api("/api/tables");
    renderTables(data.tables);
  } catch (e) {
    list.innerHTML = `<li style="color:var(--danger)">${e.message}</li>`;
  }
}

function renderTables(tables) {
  const list = document.getElementById("tableList");
  const filter = document.getElementById("tableSearch").value.toUpperCase();
  list.innerHTML = "";
  tables
    .filter((t) => t.name.toUpperCase().includes(filter))
    .forEach((t) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${t.name}</span><span class="kind">${t.kind}</span>`;
      if (t.name === state.table) li.classList.add("active");
      li.onclick = () => selectTable(t.name);
      list.appendChild(li);
    });
  window.__tables = tables;
}

// ---------------------------------------------------------------- selection
async function selectTable(name) {
  state.table = name;
  state.filters = {};
  state.page = 1;
  document.getElementById("emptyState").classList.add("hidden");
  document.getElementById("tableView").classList.remove("hidden");
  document.getElementById("currentTable").textContent = name;
  renderTables(window.__tables || []);
  try {
    const meta = await api(`/api/tables/${encodeURIComponent(name)}/columns`);
    state.columns = meta.columns;
    populateBulkColumns();
    await loadData();
  } catch (e) {
    toast(e.message, "err");
  }
}

// ---------------------------------------------------------------- data grid
async function loadData() {
  const params = new URLSearchParams();
  params.set("page", state.page);
  params.set("page_size", state.pageSize);
  for (const [col, val] of Object.entries(state.filters)) {
    if (val) params.set("f_" + col, val);
  }
  try {
    const data = await api(
      `/api/tables/${encodeURIComponent(state.table)}/data?` + params.toString()
    );
    state.total = data.total;
    renderGrid(data);
  } catch (e) {
    toast(e.message, "err");
  }
}

function renderGrid(data) {
  const headerRow = document.getElementById("headerRow");
  const filterRow = document.getElementById("filterRow");
  const body = document.getElementById("dataBody");
  headerRow.innerHTML = "";
  filterRow.innerHTML = "";
  body.innerHTML = "";

  data.columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);

    const fth = document.createElement("th");
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "search…";
    input.value = state.filters[col] || "";
    input.oninput = debounce((e) => {
      state.filters[col] = e.target.value;
      state.page = 1;
      loadData();
    }, 350);
    fth.appendChild(input);
    filterRow.appendChild(fth);
  });

  data.rows.forEach((row) => {
    const tr = document.createElement("tr");
    data.columns.forEach((col) => {
      const td = document.createElement("td");
      const val = row[col];
      if (val === null || val === undefined) {
        td.textContent = "(null)";
        td.classList.add("null");
      } else {
        td.textContent = String(val);
      }
      td.dataset.column = col;
      td.dataset.rowid = row["__ROWID__"];
      td.ondblclick = () => beginEdit(td, val);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

  const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
  document.getElementById("pageInfo").textContent =
    `Page ${state.page} / ${pages}  ·  ${state.total} rows`;
  document.getElementById("prevPage").disabled = state.page <= 1;
  document.getElementById("nextPage").disabled = state.page >= pages;
}

// ---------------------------------------------------------------- inline edit
function beginEdit(td, currentVal) {
  if (td.classList.contains("editing")) return;
  const original = currentVal === null || currentVal === undefined ? "" : String(currentVal);
  td.classList.add("editing");
  td.innerHTML = "";
  const input = document.createElement("input");
  input.className = "cell-edit";
  input.value = original;
  td.appendChild(input);
  input.focus();
  input.select();

  let done = false;
  const commit = async () => {
    if (done) return;
    done = true;
    const newVal = input.value;
    if (newVal === original) return restore(td, currentVal);
    try {
      await api(`/api/tables/${encodeURIComponent(state.table)}/cell`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rowid: td.dataset.rowid,
          column: td.dataset.column,
          value: newVal === "" ? null : newVal,
        }),
      });
      restore(td, newVal === "" ? null : newVal);
      toast(`Updated ${td.dataset.column}`, "ok");
    } catch (e) {
      restore(td, currentVal);
      toast(e.message, "err");
    }
  };

  input.onblur = commit;
  input.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    else if (e.key === "Escape") { done = true; restore(td, currentVal); }
  };
}

function restore(td, val) {
  td.classList.remove("editing");
  if (val === null || val === undefined) {
    td.textContent = "(null)";
    td.classList.add("null");
  } else {
    td.textContent = String(val);
    td.classList.remove("null");
  }
}

// ---------------------------------------------------------------- bulk update
function populateBulkColumns() {
  const sel = document.getElementById("bulkColumn");
  sel.innerHTML = "";
  state.columns.forEach((c) => {
    const o = document.createElement("option");
    o.value = c.name;
    o.textContent = `${c.name} (${c.type})`;
    sel.appendChild(o);
  });
}

function openBulk() {
  document.getElementById("bulkResult").textContent = "";
  document.getElementById("bulkApply").disabled = true;
  state.bulkPreviewOk = false;
  document.getElementById("bulkModal").classList.remove("hidden");
}
function closeBulk() {
  document.getElementById("bulkModal").classList.add("hidden");
}

function bulkPayload(preview) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      column: document.getElementById("bulkColumn").value,
      value: document.getElementById("bulkValue").value,
      condition: document.getElementById("bulkCondition").value,
      preview,
    }),
  };
}

async function bulkPreview() {
  const res = document.getElementById("bulkResult");
  try {
    const data = await api(
      `/api/tables/${encodeURIComponent(state.table)}/bulk-update`,
      bulkPayload(true)
    );
    res.className = "bulk-result ok";
    res.textContent = `${data.matched} row(s) match. Review, then Apply.`;
    state.bulkPreviewOk = data.matched >= 0;
    document.getElementById("bulkApply").disabled = false;
  } catch (e) {
    res.className = "bulk-result err";
    res.textContent = e.message;
    document.getElementById("bulkApply").disabled = true;
  }
}

async function bulkApply() {
  if (!state.bulkPreviewOk) return;
  const col = document.getElementById("bulkColumn").value;
  const val = document.getElementById("bulkValue").value;
  if (!confirm(`Set ${col} = ${val} for the matching rows?`)) return;
  const res = document.getElementById("bulkResult");
  try {
    const data = await api(
      `/api/tables/${encodeURIComponent(state.table)}/bulk-update`,
      bulkPayload(false)
    );
    res.className = "bulk-result ok";
    res.textContent = `Updated ${data.updated} row(s).`;
    toast(`Updated ${data.updated} row(s)`, "ok");
    document.getElementById("bulkApply").disabled = true;
    await loadData();
  } catch (e) {
    res.className = "bulk-result err";
    res.textContent = e.message;
  }
}

// ---------------------------------------------------------------- wiring
function init() {
  loadConfig();
  loadTables();

  document.getElementById("refreshTables").onclick = loadTables;
  document.getElementById("tableSearch").oninput = () =>
    renderTables(window.__tables || []);
  document.getElementById("reload").onclick = loadData;

  document.getElementById("prevPage").onclick = () => {
    if (state.page > 1) { state.page--; loadData(); }
  };
  document.getElementById("nextPage").onclick = () => {
    state.page++; loadData();
  };
  document.getElementById("pageSize").onchange = (e) => {
    state.pageSize = parseInt(e.target.value, 10);
    state.page = 1;
    loadData();
  };

  document.getElementById("openBulk").onclick = openBulk;
  document.getElementById("bulkCancel").onclick = closeBulk;
  document.getElementById("bulkPreview").onclick = bulkPreview;
  document.getElementById("bulkApply").onclick = bulkApply;
  // Re-arm preview if the user changes the form after previewing.
  ["bulkColumn", "bulkValue", "bulkCondition"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      document.getElementById("bulkApply").disabled = true;
      state.bulkPreviewOk = false;
    });
  });
}

document.addEventListener("DOMContentLoaded", init);
