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

  global.MiniBarChart = MiniBarChart;
})(window);
