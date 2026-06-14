/* Dashboard wiring: sidebar nav, charts, lazy per-view loading, auto-refresh. */
(function () {
  "use strict";

  var REFRESH_MS = 60000;
  var current = "overview";
  var periods = { reg: "day", doctor: "day", nurse: "day" };
  var charts = {};      // lazily created chart instances
  var loaded = {};      // which views have been loaded at least once

  function $(id) { return document.getElementById(id); }
  function setText(id, v) { var el = $(id); if (el) el.textContent = (v === null || v === undefined) ? "—" : v; }

  async function getJSON(url) {
    var res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(url + " -> " + res.status);
    return res.json();
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---- health (shared) ----
  async function loadHealth() {
    try {
      var h = await getJSON("/api/health");
      $("db-dot").className = "dot " + (h.ok ? "ok" : "bad");
      $("db-text").textContent = h.ok ? "Connected" : "Unreachable";
    } catch (e) {
      $("db-dot").className = "dot bad";
      $("db-text").textContent = "Unreachable";
    }
  }

  // ---- overview ----
  async function loadSummary() {
    var d = await getJSON("/api/summary");
    var r = d.registrations || {};
    setText("reg-today", r.today); setText("reg-week", r.this_week);
    setText("reg-month", r.this_month); setText("reg-total", r.total);
    var e = d.encounters_today || {};
    setText("enc-total", e.total); setText("enc-urgent", e.urgent_care);
    setText("enc-consult", e.consult); setText("enc-nonconsult", e.non_consult);
    setText("enc-consulted", e.consulted);
  }

  async function loadRegChart() {
    var d = await getJSON("/api/registrations?period=" + periods.reg);
    var empty = $("reg-empty");
    if (!charts.reg) charts.reg = new MiniBarChart($("reg-chart"));
    if (!d.values || d.values.length === 0) { empty.hidden = false; charts.reg.render({ labels: [], values: [] }); return; }
    empty.hidden = true;
    charts.reg.render({ labels: d.labels, values: d.values });
  }

  async function loadDoctorChart() {
    var d = await getJSON("/api/encounters/doctor-trend?period=" + periods.doctor);
    var empty = $("doctor-empty");
    if (!charts.doctor) charts.doctor = new MiniLineChart($("doctor-chart"));
    if (!d.series || d.series.length === 0) { empty.hidden = false; charts.doctor.render({ labels: [], series: [] }); return; }
    empty.hidden = true;
    charts.doctor.render({ labels: d.labels, series: d.series });
  }

  async function loadDoctorTable() {
    var rows = await getJSON("/api/doctors/today");
    var tb = $("doctor-table").querySelector("tbody");
    if (!rows || rows.length === 0) { tb.innerHTML = '<tr><td colspan="2" class="muted">No encounters today.</td></tr>'; return; }
    tb.innerHTML = rows.map(function (r) {
      return "<tr><td>" + escapeHtml(r.doctor) + '</td><td class="num">' + r.cnt + "</td></tr>";
    }).join("");
  }

  async function loadOverview() {
    await Promise.allSettled([loadSummary(), loadRegChart(), loadDoctorChart(), loadDoctorTable()]);
  }

  // ---- nurse ----
  async function loadNurseSummary() {
    var d = await getJSON("/api/nurse/summary");
    setText("nur-notes", d.notes_patients); setText("nur-vpat", d.vitals_patients);
    setText("nur-vrec", d.vitals_records); setText("nur-active", d.nurses_active);
  }

  async function loadNurseChart() {
    var d = await getJSON("/api/nurse/trend?period=" + periods.nurse);
    var empty = $("nurse-empty");
    if (!charts.nurse) charts.nurse = new MiniLineChart($("nurse-chart"));
    var hasData = d.series && d.series.some(function (s) { return s.values.some(function (v) { return v > 0; }); });
    if (!d.labels || d.labels.length === 0 || !hasData) { empty.hidden = false; charts.nurse.render({ labels: [], series: [] }); return; }
    empty.hidden = true;
    charts.nurse.render({ labels: d.labels, series: d.series });
  }

  async function loadVitalsTable() {
    var rows = await getJSON("/api/nurse/vitals");
    var tb = $("vitals-table").querySelector("tbody");
    if (!rows || rows.length === 0) { tb.innerHTML = '<tr><td colspan="5" class="muted">No vitals entered today.</td></tr>'; return; }
    tb.innerHTML = rows.map(function (r) {
      return "<tr><td>" + escapeHtml(r.emr_date) + "</td><td>" + escapeHtml(r.mrno) +
        "</td><td>" + escapeHtml(r.vital) + "</td><td>" + escapeHtml(r.vs_phys_date) +
        "</td><td>" + escapeHtml(r.entered_by) + "</td></tr>";
    }).join("");
  }

  async function loadNurse() {
    await Promise.allSettled([loadNurseSummary(), loadNurseChart(), loadVitalsTable()]);
  }

  // ---- view orchestration ----
  function stamp() { $("updated").textContent = "Updated " + new Date().toLocaleTimeString(); }

  async function refreshActive() {
    await loadHealth();
    if (current === "overview") await loadOverview();
    else if (current === "nurse") await loadNurse();
    else if (current === "custom" && window.CustomReports) window.CustomReports.load();
    loaded[current] = true;
    stamp();
  }

  var TITLES = {
    overview: "Registrations & Encounters",
    nurse: "Nurse Analysis",
    custom: "Custom Reports",
  };

  function switchView(view) {
    if (view === current) return;
    current = view;
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === view);
    });
    document.querySelectorAll(".view").forEach(function (v) { v.hidden = true; });
    $("view-" + view).hidden = false;
    $("view-title").textContent = TITLES[view] || "";
    refreshActive();
  }

  function wireToggle(name, onChange) {
    var box = document.querySelector('[data-toggle="' + name + '"]');
    box.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-period]");
      if (!btn) return;
      periods[name] = btn.dataset.period;
      box.querySelectorAll("button").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      onChange();
    });
  }

  function init() {
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.addEventListener("click", function () { switchView(b.dataset.view); });
    });
    wireToggle("reg", loadRegChart);
    wireToggle("doctor", loadDoctorChart);
    wireToggle("nurse", loadNurseChart);
    $("refresh-btn").addEventListener("click", refreshActive);

    refreshActive();
    setInterval(refreshActive, REFRESH_MS);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
