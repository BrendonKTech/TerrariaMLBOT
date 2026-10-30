const RUNS = [
  { id: "v1", name: "Run 1", cls: "s1" },
  { id: "v2", name: "Run 2", cls: "s2" },
];
const RUN3 = { id: "v3", name: "Run 3", cls: "s3" };
const X_MAX = 85000;
const timeFmt = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
const stepFmt = s => s >= 1000 ? (s / 1000).toFixed(s % 1000 === 0 ? 0 : 1) + "k" : String(s);
const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs, parent) {
  const n = document.createElementNS(SVG, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

// Nearest point in a series to a given step, or null if that run never got there
function nearest(pts, step, tol) {
  if (!pts.length || step > pts[pts.length - 1][0] + tol) return null;
  let best = pts[0];
  for (const p of pts) if (Math.abs(p[0] - step) < Math.abs(best[0] - step)) best = p;
  return best;
}

function lineChart(host, opts) {
  const tip = document.createElement("div");
  tip.className = "tooltip";
  tip.hidden = true;
  host.appendChild(tip);
  let svg, cursorStep = null;
  const XM = opts.xMax || X_MAX, XSTEP = opts.xStep || 20000;

  function render() {
    const W = Math.max(host.clientWidth, 260);
    const H = opts.height || 250;
    const m = { l: 40, r: opts.rightPad ?? 96, t: 12, b: 28 };
    const x = s => m.l + (s / XM) * (W - m.l - m.r);
    const y = v => m.t + (1 - (v - opts.yMin) / (opts.yMax - opts.yMin)) * (H - m.t - m.b);
    if (svg) svg.remove();
    svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", tabindex: "0", "aria-label": opts.label });
    host.insertBefore(svg, tip);

    const grid = el("g", { class: "grid" }, svg);
    for (const t of opts.yTicks) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t) }, grid);
      el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", class: "tick" }, svg).textContent = opts.yFmt(t);
    }
    el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis-line" }, svg);
    for (let s = 0; s <= XM; s += XSTEP) {
      el("text", { x: x(s), y: H - m.b + 18, "text-anchor": "middle", class: "tick" }, svg).textContent = stepFmt(s);
    }
    if (opts.ref) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(opts.ref.y), y2: y(opts.ref.y), class: "ref-line" }, svg);
      el("text", { x: W - m.r, y: y(opts.ref.y) - 6, "text-anchor": "end", class: "ref-label" }, svg).textContent = opts.ref.label;
    }

    for (const s of opts.series) {
      const d = s.pts.map((p, i) => (i ? "L" : "M") + x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join("");
      el("path", { d, class: "line " + s.cls }, svg);
      const last = s.pts[s.pts.length - 1];
      el("circle", { cx: x(last[0]), cy: y(last[1]), r: 4.5, class: "dot " + s.cls }, svg);
      const lbl = el("text", { x: x(last[0]) + 9, y: y(last[1]) + (s.labelDy || 4), class: "end-label" }, svg);
      lbl.textContent = (opts.series.length > 1 ? s.name + " · " : "") + opts.vFmt(last[1]);
    }

    const cross = el("line", { y1: m.t, y2: H - m.b, class: "crosshair", visibility: "hidden" }, svg);
    const markers = opts.series.map(s => el("circle", { r: 4.5, class: "dot " + s.cls, visibility: "hidden" }, svg));
    const hit = el("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" }, svg);

    function show(step) {
      cursorStep = Math.max(0, Math.min(XM, step));
      const rows = opts.series.map(s => ({ s, p: nearest(s.pts, cursorStep, XM / 50) }));
      const anchor = rows.find(r => r.p);
      if (!anchor) { hide(); return; }
      const cx = x(anchor.p[0]);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      rows.forEach((r, i) => {
        if (r.p) { markers[i].setAttribute("cx", x(r.p[0])); markers[i].setAttribute("cy", y(r.p[1])); markers[i].setAttribute("visibility", "visible"); }
        else markers[i].setAttribute("visibility", "hidden");
      });
      tip.replaceChildren();
      const head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = "≈ " + stepFmt(anchor.p[0] < 100000 ? Math.round(anchor.p[0] / 100) * 100 : Math.round(anchor.p[0] / 1000) * 1000) + " decisions";
      tip.appendChild(head);
      for (const r of rows) {
        const row = document.createElement("div");
        row.className = "tt-row";
        const key = document.createElement("span"); key.className = "key " + r.s.cls; key.style.width = "14px";
        const val = document.createElement("strong"); val.textContent = r.p ? opts.vFmt(r.p[1]) : "not reached";
        const sub = document.createElement("span"); sub.className = "tt-sub";
        sub.textContent = (opts.series.length > 1 ? r.s.name + " · " : "") + (r.p ? timeFmt.format(new Date(r.p[2] * 1000)) : "");
        row.append(key, val, sub);
        tip.appendChild(row);
      }
      tip.hidden = false;
      const tw = tip.offsetWidth;
      const left = cx + 14 + tw > W ? cx - 14 - tw : cx + 14;
      tip.style.left = Math.max(0, left) + "px";
    }
    function hide() {
      cursorStep = null;
      tip.hidden = true;
      cross.setAttribute("visibility", "hidden");
      markers.forEach(mk => mk.setAttribute("visibility", "hidden"));
    }
    const toStep = evt => {
      const r = svg.getBoundingClientRect();
      const px = (evt.clientX - r.left) * (W / r.width);
      return ((px - m.l) / (W - m.l - m.r)) * XM;
    };
    hit.addEventListener("pointermove", e => show(toStep(e)));
    hit.addEventListener("pointerdown", e => show(toStep(e)));
    hit.addEventListener("pointerleave", hide);
    svg.addEventListener("blur", hide);
    svg.addEventListener("focus", () => show(cursorStep ?? opts.series[0].pts[opts.series[0].pts.length - 1][0]));
    svg.addEventListener("keydown", e => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      show((cursorStep ?? 0) + (e.key === "ArrowRight" ? XM / 40 : -XM / 40));
    });
  }
  render();
  let lastW = host.clientWidth;
  new ResizeObserver(() => { if (host.clientWidth !== lastW) { lastW = host.clientWidth; render(); } }).observe(host);
}

const series = key => RUNS.map(r => ({ name: r.name, cls: r.cls, pts: DATA[r.id][key] }));

lineChart(document.getElementById("chart-survival"), {
  label: "Average life per episode in seconds. Run 1 fell to 42 seconds early on and recovered to 127. Run 2 stayed at the 200 second limit.",
  series: series("survival"), yMin: 0, yMax: 220, yTicks: [0, 50, 100, 150, 200],
  yFmt: v => v + "s", vFmt: v => Math.round(v) + " s",
  ref: { y: 200, label: "200 s time limit" }, height: 260,
});
const rewardOpts = (run, label) => ({
  label, series: [{ name: run.name, cls: run.cls, pts: DATA[run.id].reward }],
  yMin: -6, yMax: 9, yTicks: [-5, 0, 5], yFmt: v => (v > 0 ? "+" : "") + v,
  vFmt: v => (v > 0 ? "+" : "") + v.toFixed(1), height: 210, rightPad: 44,
});
lineChart(document.getElementById("chart-reward-1"), rewardOpts(RUNS[0], "Run 1 reward per episode, from a low of minus 4.7 up to plus 5.4"));
lineChart(document.getElementById("chart-reward-2"), rewardOpts(RUNS[1], "Run 2 reward per episode, from plus 4.4 up to plus 7.0"));
lineChart(document.getElementById("chart-random"), {
  label: "Share of maximum randomness. Run 1 fell from 100 to 93 percent; run 2 from 100 to 95 percent so far.",
  series: series("randomness").map(s => ({ ...s, labelDy: s.cls === "s2" ? -6 : 12 })),
  yMin: 88, yMax: 100.5, yTicks: [90, 95, 100], yFmt: v => v + "%", vFmt: v => v.toFixed(1) + "%", height: 230,
});

const run3 = { xMax: 1050000, xStep: 200000 };
const one = (run, key) => [{ name: run.name, cls: run.cls, pts: DATA[run.id][key] }];
lineChart(document.getElementById("chart-survival-3"), {
  ...run3, label: "Run 3 average life per episode in seconds. It started at the 200 second limit, fell below 100 seconds by 250 thousand decisions, and ended at 76.",
  series: one(RUN3, "survival"), yMin: 0, yMax: 220, yTicks: [0, 50, 100, 150, 200],
  yFmt: v => v + "s", vFmt: v => Math.round(v) + " s", ref: { y: 200, label: "200 s time limit" }, height: 240, rightPad: 52,
});
lineChart(document.getElementById("chart-reward-3"), { ...rewardOpts(RUN3, "Run 3 reward per episode, from plus 7.0 down to minus 3.0"), ...run3, xStep: 500000 });
lineChart(document.getElementById("chart-random-3"), {
  ...run3, xStep: 500000, label: "Run 3 share of maximum randomness, from 93 percent down to 81 percent.",
  series: one(RUN3, "randomness"), yMin: 70, yMax: 100.5, yTicks: [70, 80, 90, 100],
  yFmt: v => v + "%", vFmt: v => v.toFixed(1) + "%", height: 210, rightPad: 52,
});

// Table view: every logged point, so no value is only reachable by hovering
const tbody = document.querySelector("#data-table tbody");
for (const r of [...RUNS, RUN3]) {
  const d = DATA[r.id];
  d.survival.forEach((p, i) => {
    const tr = document.createElement("tr");
    const cells = [r.name, p[0].toLocaleString("en-US"), timeFmt.format(new Date(p[2] * 1000)), Math.round(p[1]) + " s", (d.reward[i][1] > 0 ? "+" : "") + d.reward[i][1].toFixed(2)];
    cells.forEach((c, j) => { const td = document.createElement("td"); td.textContent = c; if (j) td.className = "num"; tr.appendChild(td); });
    tbody.appendChild(tr);
  });
}
