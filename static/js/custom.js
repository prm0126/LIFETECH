/* Custom Reports: builder, preview, save/edit, sidebar menu + single-report view. */
window.CustomReports = (function () {
  "use strict";

  var cache = [];        // last-known list of report metadata
  var editingId = null;  // when set, Save performs an update

  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  async function api(url, opts) {
    var res = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.error || (url + " -> " + res.status));
    return data;
  }
  function send(method, url, body) {
    return api(url, { method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  // ---- render a shaped payload (card/table/bar/line) into a container ----
  function renderShaped(container, data) {
    container.innerHTML = "";
    if (!data || data.error) {
      container.innerHTML = '<div class="report-err">' + escapeHtml((data && data.error) || "No data") + "</div>";
      return;
    }
    if (data.type === "card") {
      container.innerHTML = '<div class="big-value">' + escapeHtml(data.value == null ? "0" : data.value) +
        '</div><div class="muted">' + escapeHtml(data.label || "") + "</div>";
      return;
    }
    if (data.type === "table") {
      if (!data.rows || data.rows.length === 0) { container.innerHTML = '<p class="muted">No rows.</p>'; return; }
      var head = "<tr>" + data.columns.map(function (c) { return "<th>" + escapeHtml(c) + "</th>"; }).join("") + "</tr>";
      var rows = data.rows.map(function (r) {
        return "<tr>" + r.map(function (c) { return "<td>" + escapeHtml(c == null ? "" : c) + "</td>"; }).join("") + "</tr>";
      }).join("");
      container.innerHTML = '<div class="report-scroll"><table class="grid"><thead>' + head + "</thead><tbody>" + rows + "</tbody></table></div>";
      return;
    }
    if (data.type === "bar" || data.type === "line") {
      var hasData = data.type === "bar"
        ? (data.values && data.values.length)
        : (data.series && data.series.some(function (s) { return s.values && s.values.length; }));
      if (!hasData) { container.innerHTML = '<p class="muted">No data.</p>'; return; }
      var wrap = document.createElement("div");
      wrap.className = "report-canvas";
      var cv = document.createElement("canvas");
      wrap.appendChild(cv); container.appendChild(wrap);
      requestAnimationFrame(function () {
        if (data.type === "bar") new MiniBarChart(cv).render({ labels: data.labels, values: data.values });
        else new MiniLineChart(cv).render({ labels: data.labels, series: data.series });
      });
      return;
    }
    container.innerHTML = '<p class="muted">Unknown report type.</p>';
  }

  async function runInto(id, el) {
    el.innerHTML = '<p class="muted">Loading…</p>';
    try { renderShaped(el, await api("/api/custom/" + id + "/run")); }
    catch (e) { el.innerHTML = '<div class="report-err">' + escapeHtml(e.message) + "</div>"; }
  }

  // ---- builder ----
  function msg(text, kind) { var el = $("cq-msg"); el.textContent = text || ""; el.className = "cq-msg" + (kind ? " " + kind : ""); }

  function setEditing(item) {
    editingId = item ? item.id : null;
    $("cq-save").textContent = item ? "Update report" : "Save to menu";
    var banner = $("cq-edit-banner");
    if (banner) banner.hidden = !item;
    if (banner && item) $("cq-edit-name").textContent = item.title;
  }

  function clearForm() { $("cq-title").value = ""; $("cq-sql").value = ""; $("cq-preview-area").hidden = true; setEditing(null); }

  async function preview() {
    var area = $("cq-preview-area");
    area.hidden = false; area.innerHTML = '<p class="muted">Running…</p>'; msg("");
    try { renderShaped(area, await send("POST", "/api/custom/preview", { sql: $("cq-sql").value, type: $("cq-type").value })); }
    catch (e) { area.innerHTML = '<div class="report-err">' + escapeHtml(e.message) + "</div>"; }
  }

  async function save() {
    var body = { title: $("cq-title").value, type: $("cq-type").value, sql: $("cq-sql").value };
    msg(editingId ? "Updating…" : "Saving…");
    try {
      if (editingId) await send("PUT", "/api/custom/" + editingId, body);
      else await send("POST", "/api/custom", body);
      msg("Saved.", "ok");
      clearForm();
      await loadList();
    } catch (e) { msg(e.message, "err"); }
  }

  // ---- sidebar menu + single-report view ----
  function buildNav(items) {
    var nav = $("report-nav");
    var wrap = $("report-nav-wrap");
    nav.innerHTML = "";
    wrap.hidden = items.length === 0;
    items.forEach(function (it) {
      var b = document.createElement("button");
      b.className = "report-nav-item";
      b.dataset.reportId = it.id;
      b.innerHTML = '<span class="rn-ico">&#9656;</span> ' + escapeHtml(it.title);
      b.addEventListener("click", function () { openReport(it.id, b); });
      nav.appendChild(b);
    });
  }

  function openReport(id, navBtn) {
    var item = cache.filter(function (x) { return x.id === id; })[0];
    if (!item) return;
    window.Dash.openView("report", item.title);
    document.querySelectorAll(".report-nav-item").forEach(function (b) { b.classList.remove("active"); });
    if (navBtn) navBtn.classList.add("active");
    else { var el = document.querySelector('.report-nav-item[data-report-id="' + id + '"]'); if (el) el.classList.add("active"); }
    runInto(id, $("rv-body"));
    $("rv-refresh").onclick = function () { runInto(id, $("rv-body")); };
    $("rv-edit").onclick = function () { startEdit(item); };
    $("rv-del").onclick = function () { removeReport(id); };
  }

  function startEdit(item) {
    window.Dash.openView("custom", "Custom Reports");
    document.querySelector('.nav-item[data-view="custom"]').classList.add("active");
    $("cq-title").value = item.title;
    $("cq-type").value = item.type;
    $("cq-sql").value = item.sql;
    setEditing(item);
    loadList();
  }

  async function removeReport(id) {
    if (!window.confirm("Delete this report?")) return;
    try {
      await api("/api/custom/" + id, { method: "DELETE" });
      if (editingId === id) clearForm();
      await loadList();
      window.Dash.openView("custom", "Custom Reports");
      document.querySelector('.nav-item[data-view="custom"]').classList.add("active");
    } catch (e) { /* ignore */ }
  }

  // ---- saved-reports grid (inside the builder page) ----
  function renderGrid(items) {
    var list = $("cq-list");
    if (!items || items.length === 0) { list.innerHTML = '<p class="muted">No custom reports yet. Build one above.</p>'; return; }
    list.innerHTML = "";
    items.forEach(function (it) {
      var card = document.createElement("div"); card.className = "report";
      var head = document.createElement("div"); head.className = "report-head";
      head.innerHTML = "<h4>" + escapeHtml(it.title) + "</h4>";
      var tools = document.createElement("div"); tools.className = "rv-actions";
      var openB = document.createElement("button"); openB.className = "btn"; openB.textContent = "Open";
      openB.addEventListener("click", function () { openReport(it.id); });
      var delB = document.createElement("button"); delB.className = "report-del"; delB.title = "Delete"; delB.innerHTML = "&times;";
      delB.addEventListener("click", function () { removeReport(it.id); });
      tools.appendChild(openB); tools.appendChild(delB);
      head.appendChild(tools);
      var body = document.createElement("div");
      card.appendChild(head); card.appendChild(body); list.appendChild(card);
      runInto(it.id, body);
    });
  }

  async function fetchList() {
    try { cache = await api("/api/custom"); } catch (e) { cache = []; }
    buildNav(cache);
    return cache;
  }

  async function loadList() { renderGrid(await fetchList()); }

  // refresh just the sidebar menu (used at startup)
  async function refreshNav() { await fetchList(); }

  var wired = false;
  function wire() {
    if (wired) return; wired = true;
    $("cq-preview").addEventListener("click", preview);
    $("cq-save").addEventListener("click", save);
    var cancel = $("cq-edit-cancel");
    if (cancel) cancel.addEventListener("click", clearForm);
  }

  function load() { wire(); loadList(); }

  return { load: load, refreshNav: refreshNav };
})();
