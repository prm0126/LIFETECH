/* Custom Reports: build, preview, save and render user-defined SQL reports. */
window.CustomReports = (function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  async function getJSON(url, opts) {
    var res = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.error || (url + " -> " + res.status));
    return data;
  }
  function postJSON(url, body) {
    return getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  // Render a shaped payload (card/table/bar/line) into a container element.
  function renderShaped(container, data) {
    container.innerHTML = "";
    if (!data || data.error) {
      container.innerHTML = '<div class="report-err">' + escapeHtml(data && data.error || "No data") + "</div>";
      return;
    }
    if (data.type === "card") {
      var v = data.value;
      container.innerHTML = '<div class="big-value">' + escapeHtml(v == null ? "0" : v) +
        '</div><div class="muted">' + escapeHtml(data.label || "") + "</div>";
      return;
    }
    if (data.type === "table") {
      if (!data.rows || data.rows.length === 0) { container.innerHTML = '<p class="muted">No rows.</p>'; return; }
      var head = "<tr>" + data.columns.map(function (c) { return "<th>" + escapeHtml(c) + "</th>"; }).join("") + "</tr>";
      var body = data.rows.map(function (r) {
        return "<tr>" + r.map(function (c) { return "<td>" + escapeHtml(c == null ? "" : c) + "</td>"; }).join("") + "</tr>";
      }).join("");
      container.innerHTML = '<div class="report-scroll"><table class="grid"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
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
      wrap.appendChild(cv);
      container.appendChild(wrap);
      // canvas must be in the DOM and sized before drawing
      requestAnimationFrame(function () {
        if (data.type === "bar") new MiniBarChart(cv).render({ labels: data.labels, values: data.values });
        else new MiniLineChart(cv).render({ labels: data.labels, series: data.series });
      });
      return;
    }
    container.innerHTML = '<p class="muted">Unknown report type.</p>';
  }

  function msg(text, kind) {
    var el = $("cq-msg");
    el.textContent = text || "";
    el.className = "cq-msg" + (kind ? " " + kind : "");
  }

  async function preview() {
    var area = $("cq-preview-area");
    area.hidden = false;
    area.innerHTML = '<p class="muted">Running&hellip;</p>';
    msg("");
    try {
      var data = await postJSON("/api/custom/preview", { sql: $("cq-sql").value, type: $("cq-type").value });
      renderShaped(area, data);
    } catch (e) {
      area.innerHTML = '<div class="report-err">' + escapeHtml(e.message) + "</div>";
    }
  }

  async function save() {
    msg("Saving…");
    try {
      await postJSON("/api/custom", {
        title: $("cq-title").value, type: $("cq-type").value, sql: $("cq-sql").value,
      });
      msg("Saved.", "ok");
      $("cq-title").value = "";
      $("cq-sql").value = "";
      $("cq-preview-area").hidden = true;
      loadList();
    } catch (e) {
      msg(e.message, "err");
    }
  }

  async function runOne(item, bodyEl) {
    bodyEl.innerHTML = '<p class="muted">Loading…</p>';
    try {
      var data = await getJSON("/api/custom/" + item.id + "/run");
      renderShaped(bodyEl, data);
    } catch (e) {
      bodyEl.innerHTML = '<div class="report-err">' + escapeHtml(e.message) + "</div>";
    }
  }

  async function del(id) {
    if (!window.confirm("Delete this report?")) return;
    try { await getJSON("/api/custom/" + id, { method: "DELETE" }); loadList(); } catch (e) { /* ignore */ }
  }

  async function loadList() {
    var list = $("cq-list");
    var items;
    try { items = await getJSON("/api/custom"); }
    catch (e) { list.innerHTML = '<p class="report-err">' + escapeHtml(e.message) + "</p>"; return; }
    if (!items || items.length === 0) { list.innerHTML = '<p class="muted">No custom reports yet. Build one above.</p>'; return; }
    list.innerHTML = "";
    items.forEach(function (it) {
      var card = document.createElement("div");
      card.className = "report";
      var head = document.createElement("div");
      head.className = "report-head";
      head.innerHTML = "<h4>" + escapeHtml(it.title) + "</h4>";
      var delBtn = document.createElement("button");
      delBtn.className = "report-del"; delBtn.title = "Delete"; delBtn.innerHTML = "&times;";
      delBtn.addEventListener("click", function () { delById(it.id); });
      head.appendChild(delBtn);
      var body = document.createElement("div");
      card.appendChild(head);
      card.appendChild(body);
      list.appendChild(card);
      runOne(it, body);
    });
  }

  function delById(id) { del(id); }

  var wired = false;
  function wire() {
    if (wired) return;
    wired = true;
    $("cq-preview").addEventListener("click", preview);
    $("cq-save").addEventListener("click", save);
  }

  function load() { wire(); loadList(); }

  return { load: load };
})();
