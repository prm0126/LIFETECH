/* Dashboard data loading + wiring. */
(function () {
  "use strict";

  const REFRESH_MS = 60000; // auto-refresh every 60s
  let chart = null;
  let currentPeriod = "day";

  function $(id) { return document.getElementById(id); }

  function setText(id, val) {
    const el = $(id);
    if (el) el.textContent = (val === null || val === undefined) ? "—" : val;
  }

  async function getJSON(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(url + " -> " + res.status);
    return res.json();
  }

  async function loadHealth() {
    try {
      const h = await getJSON("/api/health");
      $("db-dot").className = "dot " + (h.ok ? "ok" : "bad");
      $("db-text").textContent = h.ok ? "Database connected" : "Database unreachable";
    } catch (e) {
      $("db-dot").className = "dot bad";
      $("db-text").textContent = "Database unreachable";
    }
  }

  async function loadSummary() {
    const data = await getJSON("/api/summary");
    const r = data.registrations || {};
    setText("reg-today", r.today);
    setText("reg-week", r.this_week);
    setText("reg-month", r.this_month);
    setText("reg-total", r.total);

    const e = data.encounters_today || {};
    setText("enc-total", e.total);
    setText("enc-urgent", e.urgent_care);
    setText("enc-consult", e.consult);
    setText("enc-nonconsult", e.non_consult);
    setText("enc-consulted", e.consulted);
  }

  async function loadChart(period) {
    const data = await getJSON("/api/registrations?period=" + period);
    const empty = $("chart-empty");
    if (!data.values || data.values.length === 0) {
      empty.hidden = false;
      chart.render({ labels: [], values: [] });
      return;
    }
    empty.hidden = true;
    chart.render({ labels: data.labels, values: data.values });
  }

  async function loadDoctors() {
    const rows = await getJSON("/api/doctors/today");
    const tbody = $("doctor-table").querySelector("tbody");
    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="2" class="muted">No encounters today.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return "<tr><td>" + escapeHtml(r.doctor) + '</td><td class="num">' + r.cnt + "</td></tr>";
    }).join("");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function stamp() {
    const d = new Date();
    $("updated").textContent = "Updated " + d.toLocaleTimeString();
  }

  async function refreshAll() {
    await Promise.allSettled([
      loadHealth(),
      loadSummary(),
      loadChart(currentPeriod),
      loadDoctors(),
    ]);
    stamp();
  }

  function init() {
    chart = new MiniBarChart($("reg-chart"));

    $("period-toggle").addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-period]");
      if (!btn) return;
      currentPeriod = btn.dataset.period;
      this.querySelectorAll("button").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      loadChart(currentPeriod);
    });

    $("refresh-btn").addEventListener("click", refreshAll);

    refreshAll();
    setInterval(refreshAll, REFRESH_MS);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
