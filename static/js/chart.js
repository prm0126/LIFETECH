/*
 * Tiny dependency-free bar chart for the LIFETECH dashboard.
 * Renders a responsive bar chart onto a <canvas> with gridlines, axis labels
 * and a hover tooltip. No external libraries -> works on an air-gapped LAN.
 *
 *   const chart = new MiniBarChart(canvasEl);
 *   chart.render({ labels: [...], values: [...] });
 */
(function (global) {
  "use strict";

  const COLORS = {
    bar: "#2f6fed",
    barTop: "#5b8bf7",
    grid: "#e6e9f2",
    axis: "#7b859c",
    tooltipBg: "#1f2a44",
  };

  function MiniBarChart(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.data = { labels: [], values: [] };
    this.hover = -1;

    this._onMove = this._onMove.bind(this);
    this._onLeave = this._onLeave.bind(this);
    this._onResize = this._onResize.bind(this);

    canvas.addEventListener("mousemove", this._onMove);
    canvas.addEventListener("mouseleave", this._onLeave);
    window.addEventListener("resize", this._onResize);
  }

  MiniBarChart.prototype.render = function (data) {
    this.data = data || { labels: [], values: [] };
    this._draw();
  };

  MiniBarChart.prototype._dims = function () {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: rect.width, h: rect.height };
  };

  MiniBarChart.prototype._layout = function (w, h) {
    const pad = { l: 44, r: 16, t: 16, b: 46 };
    return {
      pad: pad,
      plotW: w - pad.l - pad.r,
      plotH: h - pad.t - pad.b,
    };
  };

  MiniBarChart.prototype._niceMax = function (max) {
    if (max <= 0) return 5;
    const pow = Math.pow(10, Math.floor(Math.log10(max)));
    const norm = max / pow;
    let step;
    if (norm <= 1) step = 1; else if (norm <= 2) step = 2;
    else if (norm <= 5) step = 5; else step = 10;
    return step * pow * Math.ceil(max / (step * pow));
  };

  MiniBarChart.prototype._bars = function () {
    const { w, h } = this._dims();
    const lay = this._layout(w, h);
    const vals = this.data.values;
    const n = vals.length;
    const max = this._niceMax(Math.max(1, ...vals));
    const gap = Math.min(18, lay.plotW / Math.max(n, 1) * 0.3);
    const bw = n ? (lay.plotW / n) - gap : 0;
    const bars = [];
    for (let i = 0; i < n; i++) {
      const x = lay.pad.l + i * (bw + gap) + gap / 2;
      const bh = (vals[i] / max) * lay.plotH;
      const y = lay.pad.t + lay.plotH - bh;
      bars.push({ x, y, w: bw, h: bh, val: vals[i], label: this.data.labels[i] });
    }
    return { bars, lay, max, w, h };
  };

  MiniBarChart.prototype._draw = function () {
    const ctx = this.ctx;
    const { bars, lay, max, w, h } = this._bars();
    ctx.clearRect(0, 0, w, h);

    // y gridlines + labels
    ctx.font = "11px -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.fillStyle = COLORS.axis;
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    const ticks = 4;
    for (let t = 0; t <= ticks; t++) {
      const val = Math.round((max / ticks) * t);
      const y = lay.pad.t + lay.plotH - (val / max) * lay.plotH;
      ctx.beginPath();
      ctx.moveTo(lay.pad.l, y);
      ctx.lineTo(lay.pad.l + lay.plotW, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(String(val), lay.pad.l - 8, y);
    }

    // bars
    bars.forEach((b, i) => {
      const grad = ctx.createLinearGradient(0, b.y, 0, b.y + b.h);
      grad.addColorStop(0, i === this.hover ? "#7aa2f9" : COLORS.barTop);
      grad.addColorStop(1, COLORS.bar);
      ctx.fillStyle = grad;
      const r = Math.min(4, b.w / 2);
      roundRectTop(ctx, b.x, b.y, Math.max(b.w, 1), b.h, r);
      ctx.fill();
    });

    // x labels (thinned to avoid overlap)
    ctx.fillStyle = COLORS.axis;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const every = Math.ceil(bars.length / 12);
    bars.forEach((b, i) => {
      if (i % every !== 0 && i !== bars.length - 1) return;
      ctx.fillText(shortLabel(b.label), b.x + b.w / 2, lay.pad.t + lay.plotH + 8);
    });

    // tooltip
    if (this.hover >= 0 && bars[this.hover]) {
      const b = bars[this.hover];
      const text = b.label + "  •  " + b.val;
      ctx.font = "12px -apple-system, Segoe UI, Roboto, sans-serif";
      const tw = ctx.measureText(text).width + 16;
      let tx = b.x + b.w / 2 - tw / 2;
      tx = Math.max(2, Math.min(tx, w - tw - 2));
      const ty = Math.max(2, b.y - 30);
      ctx.fillStyle = COLORS.tooltipBg;
      roundRect(ctx, tx, ty, tw, 22, 5);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, tx + tw / 2, ty + 11);
    }
    this._barCache = bars;
  };

  MiniBarChart.prototype._onMove = function (e) {
    if (!this._barCache) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let found = -1;
    this._barCache.forEach((b, i) => {
      if (x >= b.x && x <= b.x + b.w && y >= b.y - 6) found = i;
    });
    if (found !== this.hover) { this.hover = found; this._draw(); }
  };

  MiniBarChart.prototype._onLeave = function () {
    if (this.hover !== -1) { this.hover = -1; this._draw(); }
  };

  MiniBarChart.prototype._onResize = function () {
    clearTimeout(this._rt);
    this._rt = setTimeout(() => this._draw(), 120);
  };

  function roundRectTop(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x, y + h);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h);
    ctx.closePath();
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function shortLabel(l) {
    if (!l) return "";
    // "2026-06-13" -> "06-13" ; "2026-06" -> "2026-06"
    if (/^\d{4}-\d{2}-\d{2}$/.test(l)) return l.slice(5);
    return l;
  }

  /* ----------------------------------------------------------------------
   * MiniLineChart — multi-series line chart with legend + hover tooltip.
   *   new MiniLineChart(canvas).render({ labels:[...], series:[{name,values}] });
   * -------------------------------------------------------------------- */
  var SERIES_COLORS = [
    "#2f6fed", "#1faa59", "#f0a020", "#e2433f", "#7c4dff",
    "#12a8a8", "#d4499b", "#6b7280", "#0ea5e9", "#84cc16",
  ];

  function MiniLineChart(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.data = { labels: [], series: [] };
    this.hover = -1;
    this._onMove = this._onMove.bind(this);
    this._onLeave = this._onLeave.bind(this);
    this._onResize = this._onResize.bind(this);
    canvas.addEventListener("mousemove", this._onMove);
    canvas.addEventListener("mouseleave", this._onLeave);
    window.addEventListener("resize", this._onResize);
  }

  MiniLineChart.prototype.render = function (data) {
    this.data = data || { labels: [], series: [] };
    this._draw();
  };

  MiniLineChart.prototype._dims = MiniBarChart.prototype._dims;
  MiniLineChart.prototype._niceMax = MiniBarChart.prototype._niceMax;

  MiniLineChart.prototype._layout = function (w, h, legendRows) {
    var pad = { l: 44, r: 16, t: 16, b: 46 + legendRows * 20 };
    return { pad: pad, plotW: w - pad.l - pad.r, plotH: h - pad.t - pad.b };
  };

  MiniLineChart.prototype._draw = function () {
    var ctx = this.ctx;
    var d = this.data;
    var dim = this._dims();
    var w = dim.w, h = dim.h;
    ctx.clearRect(0, 0, w, h);
    if (!d.series || d.series.length === 0 || d.labels.length === 0) return;

    var perRow = Math.max(1, Math.floor(w / 150));
    var legendRows = Math.ceil(d.series.length / perRow);
    var lay = this._layout(w, h, legendRows);

    var maxVal = 1;
    d.series.forEach(function (s) {
      s.values.forEach(function (v) { if (v > maxVal) maxVal = v; });
    });
    var max = this._niceMax(maxVal);
    var n = d.labels.length;
    var stepX = n > 1 ? lay.plotW / (n - 1) : 0;
    var xAt = function (i) { return lay.pad.l + (n > 1 ? i * stepX : lay.plotW / 2); };
    var yAt = function (v) { return lay.pad.t + lay.plotH - (v / max) * lay.plotH; };

    // gridlines + y labels
    ctx.font = "11px -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.strokeStyle = "#e6e9f2";
    ctx.fillStyle = "#7b859c";
    ctx.lineWidth = 1;
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var val = Math.round((max / ticks) * t);
      var gy = yAt(val);
      ctx.beginPath(); ctx.moveTo(lay.pad.l, gy); ctx.lineTo(lay.pad.l + lay.plotW, gy); ctx.stroke();
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillText(String(val), lay.pad.l - 8, gy);
    }

    // x labels (thinned)
    ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = "#7b859c";
    var every = Math.ceil(n / 12);
    for (var i = 0; i < n; i++) {
      if (i % every !== 0 && i !== n - 1) continue;
      ctx.fillText(shortLabel(d.labels[i]), xAt(i), lay.pad.t + lay.plotH + 8);
    }

    // lines
    d.series.forEach(function (s, si) {
      var color = SERIES_COLORS[si % SERIES_COLORS.length];
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      s.values.forEach(function (v, i) {
        var px = xAt(i), py = yAt(v);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.stroke();
      ctx.fillStyle = color;
      s.values.forEach(function (v, i) {
        ctx.beginPath(); ctx.arc(xAt(i), yAt(v), 2.5, 0, Math.PI * 2); ctx.fill();
      });
    });

    // hover guide + tooltip
    if (this.hover >= 0 && this.hover < n) {
      var hx = xAt(this.hover);
      ctx.strokeStyle = "#c9cdd6"; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(hx, lay.pad.t); ctx.lineTo(hx, lay.pad.t + lay.plotH); ctx.stroke();
      ctx.setLineDash([]);
      var lines = [d.labels[this.hover]];
      d.series.forEach(function (s) { lines.push(s.name + ": " + (s.values[this.hover] || 0)); }, this);
      ctx.font = "12px -apple-system, Segoe UI, Roboto, sans-serif";
      var tw = 0;
      lines.forEach(function (ln) { tw = Math.max(tw, ctx.measureText(ln).width); });
      tw += 16;
      var th = lines.length * 17 + 8;
      var tx = Math.min(Math.max(hx + 10, 2), w - tw - 2);
      var ty = lay.pad.t + 4;
      ctx.fillStyle = "rgba(31,42,68,.92)";
      roundRect(ctx, tx, ty, tw, th, 6); ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "left"; ctx.textBaseline = "top";
      lines.forEach(function (ln, i) { ctx.fillText(ln, tx + 8, ty + 6 + i * 17); });
    }

    // legend
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    var ly = lay.pad.t + lay.plotH + 30;
    d.series.forEach(function (s, si) {
      var col = si % perRow, row = Math.floor(si / perRow);
      var lx = lay.pad.l + col * (lay.plotW / perRow);
      var yy = ly + row * 20;
      ctx.fillStyle = SERIES_COLORS[si % SERIES_COLORS.length];
      roundRect(ctx, lx, yy - 5, 10, 10, 2); ctx.fill();
      ctx.fillStyle = "#1f2a44";
      ctx.fillText(s.name, lx + 16, yy);
    });

    this._geom = { xAt: xAt, n: n, pad: lay.pad };
  };

  MiniLineChart.prototype._onMove = function (e) {
    if (!this._geom) return;
    var rect = this.canvas.getBoundingClientRect();
    var x = e.clientX - rect.left;
    var nearest = -1, best = 1e9;
    for (var i = 0; i < this._geom.n; i++) {
      var dx = Math.abs(this._geom.xAt(i) - x);
      if (dx < best) { best = dx; nearest = i; }
    }
    if (nearest !== this.hover) { this.hover = nearest; this._draw(); }
  };
  MiniLineChart.prototype._onLeave = function () {
    if (this.hover !== -1) { this.hover = -1; this._draw(); }
  };
  MiniLineChart.prototype._onResize = function () {
    clearTimeout(this._rt); this._rt = setTimeout(this._draw.bind(this), 120);
  };

  global.MiniBarChart = MiniBarChart;
  global.MiniLineChart = MiniLineChart;
})(window);
