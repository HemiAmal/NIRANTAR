/* NIRANTAR console. Vanilla JS, no external libraries (air-gap friendly).
   Charts are hand-drawn SVG: 2px lines, 10-14% washes, 4px rounded data-ends,
   hairline grids, legends for >= 2 series, tooltips on hover. */
"use strict";

const S = { report: null, ledger: null, scen: "normal" };
const SVGNS = "http://www.w3.org/2000/svg";
const POLICY_LABEL = {
  "P0 Reactive": "Status quo (reactive)",
  "P1 Prediction-only": "Prediction only",
  "P2 Predict+Spares+Schedule": "Prediction + spares + scheduling",
  "P2 + smart routing": "P2 + smart repair routing",
  "P2 + rogue quarantine": "P2 + rogue quarantine",
  "P2 + MRV portfolio": "P2 + priced spares portfolio",
  "P3 NIRANTAR": "NIRANTAR (all components)",
};
const ENV_NAME = { coastal_saline: "Coastal (saline)", desert_dust: "Desert (dust)", high_altitude: "High altitude", humid_ne: "Humid north-east" };
const nice = (x) => String(x).replaceAll("_", " ");
const SCEN_TEXT = {
  normal: "Normal operations: supplier conditions drift between normal and stressed at random, as they do in reality.",
  supply_shock: "Supply shock: Russian shipping, customs and payments disrupted from day 20 to day 200 (deliveries about 8x slower).",
};

// ------------------------------------------------------------ utilities
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => (x == null ? "–" : (x * 100).toFixed(d) + "%");
const pts = (x) => (x >= 0 ? "+" : "−") + Math.abs(x * 100).toFixed(1) + " pts";
const fmt = (x, d = 0) => (x == null ? "–" : Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const signed = (x, d = 0) => (x >= 0 ? "+" : "−") + fmt(Math.abs(x), d);

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function svgRoot(container, w, h) {
  container.innerHTML = "";
  const s = el("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: "img" });
  container.appendChild(s);
  return s;
}
function niceTicks(lo, hi, n = 5) {
  const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3500);
}
const tip = $("#tooltip");
function showTip(html, x, y) {
  tip.innerHTML = html; tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
  tip.style.left = left + "px"; tip.style.top = top + "px";
}
const hideTip = () => (tip.hidden = true);

function tile({ label, value, delta, up, hero, swatch }) {
  return `<div class="tile"><div class="label">${swatch ? `<span class="swatch" style="background:var(${swatch})"></span>` : ""}${esc(label)}</div>
    <div class="value${hero ? " hero" : ""}">${value}</div>${delta ? `<div class="delta${up ? " up" : ""}">${delta}</div>` : ""}</div>`;
}
function badge(level, text) { return `<span class="badge"><span class="ic ${level}"></span>${esc(text)}</span>`; }
function legend(container, items) {
  container.innerHTML = items.map((i) => `<span><i class="${i.kind || ""}" style="${i.kind === "ring" ? "" : `background:var(${i.color})`}"></i>${esc(i.label)}</span>`).join("");
}

// ------------------------------------------------------------ fan chart
function fanChart(container, series) {
  const W = Math.max(container.clientWidth, 320), H = 300;
  const m = { l: 46, r: 16, t: 12, b: 30 };
  const s = svgRoot(container, W, H);
  const all = series.flatMap((x) => [...x.data.p10, ...x.data.p90]);
  let lo = Math.max(0, Math.floor((Math.min(...all) - 0.02) * 20) / 20);
  let hi = Math.min(1, Math.ceil((Math.max(...all) + 0.02) * 20) / 20);
  const days = series[0].data.day, maxDay = days[days.length - 1];
  const X = (d) => m.l + (d / maxDay) * (W - m.l - m.r);
  const Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  for (const t of niceTicks(lo, hi, 5)) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grid" }, s);
    el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, s).textContent = Math.round(t * 100) + "%";
  }
  el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis" }, s);
  const months = Math.round(maxDay / 30.4), narrow = W < 600, stepMo = narrow ? (months > 12 ? 6 : 3) : (months > 12 ? 4 : 2);
  for (let mo = 0; mo <= months; mo += stepMo) {
    const d = Math.min(mo * 30.4, maxDay);
    el("text", { x: X(d), y: H - m.b + 18, "text-anchor": mo === 0 ? "start" : mo >= months ? "end" : "middle" }, s)
      .textContent = mo === 0 ? "Today" : narrow ? `M${mo}` : `Month ${mo}`;
  }
  for (const ser of series) {
    const d = ser.data;
    const top = days.map((day, i) => `${X(day)},${Y(d.p90[i])}`).join(" L");
    const bot = days.map((day, i) => `${X(day)},${Y(d.p10[i])}`).reverse().join(" L");
    el("path", { d: `M${top} L${bot} Z`, style: `fill:var(${ser.wash});stroke:none` }, s);
  }
  for (const ser of series) {
    const d = ser.data;
    el("path", { d: "M" + days.map((day, i) => `${X(day)},${Y(d.p50[i])}`).join(" L"),
      style: `fill:none;stroke:var(${ser.color});stroke-width:2;stroke-linejoin:round;stroke-linecap:round` }, s);
    const last = days.length - 1;
    el("circle", { cx: X(days[last]), cy: Y(d.p50[last]), r: 4, style: `fill:var(${ser.color});stroke:var(--surface-1);stroke-width:2` }, s);
  }
  // hover layer: crosshair + tooltip
  const cross = el("line", { y1: m.t, y2: H - m.b, class: "axis", visibility: "hidden" }, s);
  const dots = series.map((ser) => el("circle", { r: 4, visibility: "hidden", style: `fill:var(${ser.color});stroke:var(--surface-1);stroke-width:2` }, s));
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, s);
  hit.addEventListener("mousemove", (ev) => {
    const box = s.getBoundingClientRect(), scale = W / box.width;
    const x = (ev.clientX - box.left) * scale;
    const day = ((x - m.l) / (W - m.l - m.r)) * maxDay;
    let i = 0; for (let k = 0; k < days.length; k++) if (Math.abs(days[k] - day) < Math.abs(days[i] - day)) i = k;
    cross.setAttribute("x1", X(days[i])); cross.setAttribute("x2", X(days[i])); cross.setAttribute("visibility", "visible");
    series.forEach((ser, j) => { dots[j].setAttribute("cx", X(days[i])); dots[j].setAttribute("cy", Y(ser.data.p50[i])); dots[j].setAttribute("visibility", "visible"); });
    showTip(`<div class="t">Day ${days[i]}</div>` + series.map((ser) =>
      `<div class="r"><span><i style="background:var(${ser.color})"></i>${esc(ser.name)}</span><b>${pct(ser.data.p50[i])}</b></div>
       <div class="r muted"><span>10th–90th pct</span><span>${pct(ser.data.p10[i])} – ${pct(ser.data.p90[i])}</span></div>`).join(""), ev.clientX, ev.clientY);
  });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); });
}

// ------------------------------------------------------------ horizontal bars (single series, may be negative)
function roundedBar(x0, x1, y, h, r = 4) {
  const dir = x1 >= x0 ? 1 : -1, len = Math.abs(x1 - x0), rr = Math.min(r, len, h / 2);
  if (len < 0.5) return "";
  const xe = x1 - dir * rr;
  return `M${x0},${y} H${xe} Q${x1},${y} ${x1},${y + rr} V${y + h - rr} Q${x1},${y + h} ${xe},${y + h} H${x0} Z`;
}
function hBars(container, rows, { unit = "", digits = 0, tipFn } = {}) {
  const W = Math.max(container.clientWidth, 300);
  const stacked = W < 560;                       // narrow: label above its bar instead of beside it
  const labelW = stacked ? 8 : Math.min(250, W * 0.36), rowH = stacked ? 50 : 34, barH = 18;
  const m = { t: 8, b: 26, r: stacked ? 52 : 64 };
  const H = m.t + m.b + rows.length * rowH;
  const s = svgRoot(container, W, H);
  const vals = rows.flatMap((r) => [r.value, r.lo ?? r.value, r.hi ?? r.value, 0]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.04 || 1;
  const x0 = labelW, x1 = W - m.r;
  const X = (v) => x0 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (x1 - x0);
  for (const t of niceTicks(lo - pad, hi + pad, 5)) {
    el("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grid" }, s);
    el("text", { x: X(t), y: H - m.b + 16, "text-anchor": "middle" }, s).textContent = fmt(t, Math.abs(t) < 10 && t % 1 ? 1 : 0);
  }
  el("line", { x1: X(0), x2: X(0), y1: m.t, y2: H - m.b, class: "axis" }, s);
  rows.forEach((r, i) => {
    const y = stacked ? m.t + i * rowH + 20 : m.t + i * rowH + (rowH - barH) / 2;
    if (stacked) el("text", { x: 0, y: m.t + i * rowH + 12, "text-anchor": "start", class: "ink" }, s).textContent = r.label;
    else el("text", { x: labelW - 10, y: y + barH / 2 + 4, "text-anchor": "end", class: "ink" }, s).textContent = r.label;
    const g = el("g", {}, s);
    el("path", { d: roundedBar(X(0), X(r.value), y, barH), style: `fill:var(${r.color || "--series-1"})` }, g);
    if (r.lo != null && r.hi != null) {
      const cy = y + barH / 2;
      el("line", { x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy, style: "stroke:var(--text-secondary);stroke-width:1.5" }, g);
      for (const v of [r.lo, r.hi]) el("line", { x1: X(v), x2: X(v), y1: cy - 5, y2: cy + 5, style: "stroke:var(--text-secondary);stroke-width:1.5" }, g);
    }
    const end = r.hi != null ? (r.value >= 0 ? Math.max(r.hi, r.value) : Math.min(r.lo, r.value)) : r.value;
    el("text", { x: X(end) + (r.value >= 0 ? 6 : -6), y: y + barH / 2 + 4, "text-anchor": r.value >= 0 ? "start" : "end", class: "strong" }, g)
      .textContent = (r.value >= 0 && r.signed ? "+" : "") + fmt(r.value, digits) + unit;
    const hit = el("rect", { x: 0, y: m.t + i * rowH, width: W, height: rowH, fill: "transparent" }, g);
    hit.addEventListener("mousemove", (ev) => showTip(tipFn ? tipFn(r) : `<div class="t">${esc(r.label)}</div>${fmt(r.value, digits)}${unit}`, ev.clientX, ev.clientY));
    hit.addEventListener("mouseleave", hideTip);
  });
}

// ------------------------------------------------------------ dot plot with CI (agencies)
function dotPlot(container, rows) {
  const W = Math.max(container.clientWidth, 320), labelW = 120, rowH = 40;
  const m = { t: 8, b: 40, r: 24 };
  const H = m.t + m.b + rows.length * rowH;
  const s = svgRoot(container, W, H);
  const X = (v) => labelW + v * (W - labelW - m.r);
  for (const t of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
    el("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grid" }, s);
    el("text", { x: X(t), y: H - m.b + 16, "text-anchor": "middle" }, s).textContent = t.toFixed(1);
  }
  el("text", { x: X(0), y: H - 6, "text-anchor": "start" }, s).textContent = "← better repairs (as good as new)";
  el("text", { x: X(1), y: H - 6, "text-anchor": "end" }, s).textContent = "worse repairs (no better than before) →";
  rows.forEach((r, i) => {
    const cy = m.t + i * rowH + rowH / 2;
    el("text", { x: labelW - 12, y: cy + 4, "text-anchor": "end", class: "ink" }, s).textContent = r.label;
    el("line", { x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy, style: "stroke:var(--series-1);stroke-width:2;stroke-linecap:round" }, s);
    el("circle", { cx: X(r.truth), cy, r: 6, style: "fill:none;stroke:var(--text-secondary);stroke-width:2" }, s);
    el("circle", { cx: X(r.est), cy, r: 5, style: "fill:var(--series-1);stroke:var(--surface-1);stroke-width:2" }, s);
    const hit = el("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent" }, s);
    hit.addEventListener("mousemove", (ev) => showTip(`<div class="t">${esc(r.label)}</div>
      <div class="r"><span>Estimated q</span><b>${r.est.toFixed(2)}</b></div>
      <div class="r"><span>90% interval</span><span>${r.lo.toFixed(2)} – ${r.hi.toFixed(2)}</span></div>
      <div class="r"><span>Hidden truth</span><span>${r.truth.toFixed(2)}</span></div>`, ev.clientX, ev.clientY));
    hit.addEventListener("mouseleave", hideTip);
  });
}

// ------------------------------------------------------------ views
const expRow = (scen, policy) => S.report.experiment.find((e) => e.scenario === scen && e.policy === policy);

function renderReadiness() {
  const sc = S.scen, p0 = expRow(sc, "P0 Reactive"), p3 = expRow(sc, "P3 NIRANTAR");
  $("#scen-lede").textContent = SCEN_TEXT[sc];
  $("#tiles").innerHTML = [
    tile({ label: "NIRANTAR availability", value: pct(p3.availability), hero: true, swatch: "--series-1",
      delta: `${pts(p3.availability - p0.availability)} vs status quo`, up: p3.availability > p0.availability }),
    tile({ label: "Status quo availability", value: pct(p0.availability), swatch: "--series-2", delta: "reactive maintenance, consumption-based spares" }),
    tile({ label: "Aircraft-days recovered in 12 months", value: signed(p3.delta_waad_vs_P0),
      delta: `≈ ${p3.fighter_sqe_equivalent.toFixed(2)} fighter-squadron equivalents (95% CI ${fmt(p3.delta_waad_ci95[0])} to ${fmt(p3.delta_waad_ci95[1])})`, up: p3.delta_waad_vs_P0 > 0 }),
    tile({ label: "Worst-case availability (worst 10% of futures)", value: pct(p3.CRaR10),
      delta: `status quo ${pct(p0.CRaR10)} · ${pts(p3.CRaR10 - p0.CRaR10)}`, up: p3.CRaR10 > p0.CRaR10 }),
  ].join("");
  const fan = S.report.fan[sc];
  const series = [
    { name: "Status quo", color: "--series-2", wash: "--series-2-wash", data: fan["P0 Reactive"] },
    { name: "NIRANTAR", color: "--series-1", wash: "--series-1-wash", data: fan["P3 NIRANTAR"] },
  ];
  legend($("#fan-legend"), [{ label: "NIRANTAR (median, 10th–90th pct band)", color: "--series-1" }, { label: "Status quo", color: "--series-2" }]);
  fanChart($("#fan"), series);
  const rows = S.report.experiment.filter((e) => e.scenario === sc && e.policy !== "P0 Reactive").map((e) => ({
    label: POLICY_LABEL[e.policy] || e.policy, value: e.delta_waad_vs_P0, lo: e.delta_waad_ci95[0], hi: e.delta_waad_ci95[1], signed: true,
    e,
  }));
  hBars($("#policy-bars"), rows, { tipFn: (r) => `<div class="t">${esc(r.label)}</div>
    <div class="r"><span>Δ aircraft-days</span><b>${signed(r.value)}</b></div>
    <div class="r"><span>95% CI</span><span>${fmt(r.lo)} to ${fmt(r.hi)}</span></div>
    <div class="r"><span>Availability</span><span>${pct(r.e.availability)}</span></div>
    <div class="r"><span>Worst-10% availability</span><span>${pct(r.e.CRaR10)}</span></div>` });
  $("#policy-table").innerHTML = `<table><thead><tr><th>Policy</th><th class="num">Availability</th><th class="num">95% CI</th>
    <th class="num">Fighters</th><th class="num">Helicopters</th><th class="num">Worst-10%</th><th class="num">Δ aircraft-days</th><th class="num">Preventive swaps</th></tr></thead><tbody>` +
    S.report.experiment.filter((e) => e.scenario === sc).map((e) => `<tr><td>${esc(POLICY_LABEL[e.policy] || e.policy)}</td>
      <td class="num">${pct(e.availability)}</td><td class="num">${pct(e.ci95[0])}–${pct(e.ci95[1])}</td><td class="num">${pct(e.fighter)}</td>
      <td class="num">${pct(e.helo)}</td><td class="num">${pct(e.CRaR10)}</td><td class="num">${signed(e.delta_waad_vs_P0)}</td><td class="num">${fmt(e.preventive_swaps)}</td></tr>`).join("") + "</tbody></table>";
}

function decisionsBySeq() {
  const out = {};
  for (const e of S.ledger?.entries || []) if (e.kind === "decision" && e.payload && e.payload.recommendation_seq != null) out[e.payload.recommendation_seq] = e;
  return out;
}
const GRADE = { E1: ["good", "E1 strong"], E2: ["good", "E2 good"], E3: ["warning", "E3 moderate"], E4: ["serious", "E4 weak"], E5: ["critical", "E5 insufficient"] };

function renderOpportunities() {
  const dec = decisionsBySeq();
  const rows = S.report.opportunities;
  $("#opp-table").innerHTML = `<p class="hint">Value certainty comes from the simulation interval; data evidence grades the records behind it (SATYA).
    An action is decision-grade only when both are strong.</p><table><thead><tr><th>Action</th><th class="num">Value (wAAD)</th><th class="num">95% CI</th><th class="num">Futures where it helps</th>
    <th class="num">Cost (₹ lakh)</th><th>Value certainty</th><th>Data evidence</th><th>Who decides</th><th>Why</th><th>Decision</th></tr></thead><tbody>` +
    rows.map((r) => {
      const d = dec[r.ledger_seq], [lvl, txt] = GRADE[r.evidence_grade] || ["neutral", r.evidence_grade];
      const cert = (r.ci95[0] === 0 && r.ci95[1] === 0) ? badge("neutral", "No effect within horizon")
        : r.ci95[0] > 0 ? badge("good", "Clearly positive") : r.ci95[1] < 0 ? badge("critical", "Likely harmful")
        : badge("warning", "Uncertain, needs more evidence");
      return `<tr><td>${esc(r.action)}</td><td class="num">${signed(r.mrv_aad, 1)}</td>
        <td class="num">${fmt(r.ci95[0], 1)} to ${fmt(r.ci95[1], 1)}</td><td class="num">${Math.round(r.p_positive * 100)}%</td>
        <td class="num">${fmt(r.cost_lakh)}</td><td>${cert}</td><td>${badge(lvl, "Data " + txt)}</td><td>${esc(r.authority)}</td>
        <td class="expl">${esc(r.explanation)}</td>
        <td><div class="decide" data-seq="${r.ledger_seq}">
          ${d ? `<span class="done">${esc(d.payload.verdict)} by ${esc(d.actor)} · #${d.seq}</span>` : ""}
          <button data-v="accept">Accept</button><button data-v="defer">Defer</button><button data-v="reject">Reject</button></div></td></tr>`;
    }).join("") + "</tbody></table>";
  $("#opp-table").querySelectorAll(".decide button").forEach((b) => b.addEventListener("click", async () => {
    const seq = +b.parentElement.dataset.seq;
    try {
      const r = await api("/api/decision", { ledger_seq: seq, verdict: b.dataset.v, reason_code: "OFFICER_REVIEW" });
      toast(`Decision "${r.verdict}" signed into ledger as entry #${r.seq}`);
      S.ledger = await api("/api/ledger"); renderOpportunities(); renderLedger();
    } catch (e) { toast("Error: " + e.message); }
  }));
  const c = S.report.cost_of_delay;
  $("#cod-card").innerHTML = c ? `<h3>Cost of delay</h3><p class="lede">If <b>${esc(c.action)}</b> waits 60 days, its value falls from
    ${signed(c.mrv_now, 1)} to ${signed(c.mrv_if_delayed_60d, 1)} weighted aircraft-days: about <b>${fmt(c.cost_of_delay_waad_per_day, 2)} aircraft-days lost per day of delay</b>.</p>` : "";
}

function renderAgencies() {
  const q = S.report.dhanvantari.agency_q;
  const rows = Object.entries(q).map(([a, v]) => ({ label: a, est: v.estimate[0], lo: v.estimate[1], hi: v.estimate[2], truth: v.truth }))
    .sort((a, b) => a.est - b.est);
  legend($("#ag-legend"), [{ label: "Estimated from records (dot) with 90% interval (line)", color: "--series-1" }, { label: "Hidden truth (synthetic world only)", kind: "ring" }]);
  dotPlot($("#ag-dots"), rows);
  const r = S.report.sushruta.rogues;
  $("#rogue-tiles").innerHTML = [
    tile({ label: "Rogue serials flagged", value: fmt(r.flagged), delta: "units that keep failing after repair" }),
    tile({ label: "Correct flags (precision)", value: Math.round(r.precision * 100) + "%", delta: `${r.true_positives} of ${r.flagged} are true rogues`, up: true }),
    tile({ label: "Rogues found (recall)", value: Math.round(r.recall * 100) + "%", delta: "of planted rogues, from 5 years of records" }),
  ].join("");
  $("#ag-table").innerHTML = `<table><thead><tr><th>Agency</th><th class="num">Jobs</th><th class="num">q estimate</th><th class="num">90% interval</th>
    <th class="num">Median turnaround (days)</th><th class="num">90th pct turnaround</th><th class="num">Send-to-done median</th></tr></thead><tbody>` +
    S.report.sushruta.scorecards.map((s) => `<tr><td>${esc(s.agency)}</td><td class="num">${fmt(s.jobs)}</td><td class="num">${s.q_hat.toFixed(2)}</td>
      <td class="num">${s.q_lo.toFixed(2)}–${s.q_hi.toFixed(2)}</td><td class="num">${fmt(s.tat_median_days, 1)}</td><td class="num">${fmt(s.tat_p90_days, 1)}</td>
      <td class="num">${fmt(s.send_to_done_median_days, 1)}</td></tr>`).join("") + "</tbody></table>";
}

function renderSignals() {
  const d = S.report.drishti;
  $("#sig-tiles").innerHTML = [
    tile({ label: "Confirmed signals", value: fmt(d.signals.length), delta: `${d.false_signals} false (checked against synthetic truth)`, up: d.false_signals === 0 }),
    tile({ label: "Planted effects surfaced for review", value: `${d.planted_found_as_candidate} of ${d.planted.length}`, delta: "as candidate or confirmed signals" }),
  ].join("");
  const planted = new Set(d.planted.map((p) => p.join("|")));
  const draw = () => {
    const all = $("#sig-all").checked;
    const rows = (d.table || []).filter((r) => all || r.signal || r.candidate);
    $("#sig-table").innerHTML = `<table><thead><tr><th>Status</th><th>Part family</th><th>Environment</th><th>Failure mode</th><th class="num">Reports</th>
      <th class="num">Expected</th><th class="num">IC (lower 95%)</th><th class="num">PRR</th><th class="num">Rate ratio</th><th>Synthetic truth</th></tr></thead><tbody>` +
      rows.map((r) => `<tr><td>${r.signal ? badge("critical", "Confirmed signal") : r.candidate ? badge("warning", "Candidate") : badge("neutral", "No signal")}</td>
        <td>${esc(r.family)}</td><td>${esc(ENV_NAME[r.env] || nice(r.env))}</td><td>${esc(nice(r.mode))}</td><td class="num">${r.n_reports}</td>
        <td class="num">${fmt(r.expected, 1)}</td><td class="num">${fmt(r.IC025, 2)}</td><td class="num">${fmt(r.PRR, 2)}</td>
        <td class="num">${r.rate_ratio == null ? "–" : fmt(r.rate_ratio, 2)}</td><td>${planted.has([r.family, r.env, r.mode].join("|")) ? "planted effect" : ""}</td></tr>`).join("") +
      "</tbody></table>";
  };
  $("#sig-all").onchange = draw;
  draw();
}

function renderIndigenisation() {
  const rows = S.report.indigenisation.map((r) => ({ label: `${r.pn} ${r.name}`, value: r.waad_per_crore, r }));
  hBars($("#ind-bars"), rows, { digits: 0, tipFn: (x) => `<div class="t">${esc(x.label)} (${esc(x.r.origin)})</div>
    <div class="r"><span>Per ₹1 crore</span><b>${fmt(x.value)}</b></div>
    <div class="r"><span>Normal operations</span><span>${signed(x.r.mrv_normal)}</span></div>
    <div class="r"><span>Supply shock</span><span>${signed(x.r.mrv_shock)}</span></div>
    <div class="r"><span>Development cost</span><span>₹${fmt(x.r.cost_lakh)} lakh</span></div>` });
  $("#ind-table").innerHTML = `<table><thead><tr><th>Part</th><th>Origin</th><th class="num">Development cost (₹ lakh)</th>
    <th class="num">Value, normal</th><th class="num">Value, supply shock</th><th class="num">Tail-risk gain (pts)</th><th class="num">Per ₹1 crore</th></tr></thead><tbody>` +
    S.report.indigenisation.map((r) => `<tr><td>${esc(r.pn)} ${esc(r.name)}</td><td>${esc(r.origin)}</td><td class="num">${fmt(r.cost_lakh)}</td>
      <td class="num">${signed(r.mrv_normal)}</td><td class="num">${signed(r.mrv_shock)}</td><td class="num">${fmt(r.delta_crar_shock_pts, 2)}</td>
      <td class="num">${fmt(r.waad_per_crore)}</td></tr>`).join("") + "</tbody></table>";
}

function renderLedger() {
  const L = S.ledger, sat = S.report.satya;
  const nIssues = Object.values(sat.issues || {}).reduce((a, b) => a + b, 0);
  $("#dq-tiles").innerHTML = [
    tile({ label: "Record issues found (SATYA)", value: fmt(nIssues), delta: nIssues ? JSON.stringify(sat.issues) : "history passed all 10 invariants", up: !nIssues }),
    tile({ label: "Lowest data-quality score", value: (sat.min_dq ?? 1).toFixed(2), delta: "per part number, 1.00 = clean" }),
    tile({ label: "Signed ledger entries", value: fmt(L.count), delta: `tree head covers ${L.tree_head.size} · root ${L.tree_head.root}…` }),
  ].join("");
  $("#ledger-table").innerHTML = `<table><thead><tr><th class="num">#</th><th>Time</th><th>Kind</th><th>Signed by</th><th>Summary</th><th>Hash</th></tr></thead><tbody>` +
    L.entries.slice().reverse().map((e) => {
      const p = e.payload || {};
      const summary = e.kind === "recommendation" ? p.action : e.kind === "decision" ? `${p.verdict} recommendation #${p.recommendation_seq} (${p.reason_code})`
        : e.kind === "data_batch" ? `${p.spells} spells, ${p.repairs} repairs, ${p.snags} snags` : e.kind === "model_version" ? `${p.model}, ${p.n_failures} failures`
        : JSON.stringify(p).slice(0, 90);
      return `<tr><td class="num">${e.seq}</td><td>${new Date(e.ts * 1000).toLocaleString()}</td><td>${esc(e.kind)}</td><td>${esc(e.actor)}</td>
        <td>${esc(summary)}</td><td><code>${esc(e.hash)}</code></td></tr>`;
    }).join("") + "</tbody></table>";
}

async function verifyLedger() {
  S.ledger = await api("/api/ledger");
  renderLedger();
  const ok = S.ledger.failed.length === 0;
  $("#verify-result").innerHTML = `<div class="verify">${ok ? badge("good", "Verified") + " All " + S.ledger.count +
    " entries: signatures valid, hash chain intact, Merkle tree head matches."
    : badge("critical", "Tampering detected") + " Failed entries: " + esc(S.ledger.failed.join(", "))}</div>`;
}
async function tamperDemo() {
  const target = (S.ledger.entries.find((e) => e.kind === "decision") || S.ledger.entries[0]).seq;
  const r = await api("/api/ledger/tamper-demo", { seq: target });
  $("#verify-result").innerHTML = `<div class="verify">${badge("critical", "Tampering detected")}
    On a <b>copy</b> of the ledger, entry #${r.edited_seq} was edited:<br><code>${esc(r.before)}</code><br>→ <code>${esc(r.after)}</code><br>
    Verification flagged: <b>${esc(r.detected.map((x) => (x === -1 ? "tree head" : "#" + x)).join(", "))}</b>.
    ${r.real_ledger_intact ? badge("good", "Real ledger intact") : ""}</div>`;
}

// ------------------------------------------------------------ live what-if
async function runSim(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target), body = Object.fromEntries(f.entries());
  for (const k of ["shock_start", "shock_days", "seeds"]) body[k] = +body[k];
  const btn = ev.target.querySelector("button"); btn.disabled = true;
  $("#sim-status").textContent = "Running the digital twin… (first run also rebuilds the model, ~10 s)";
  try {
    const [a, b] = await Promise.all([api("/api/simulate", body), api("/api/simulate", { ...body, policy: "P0" })]);
    const series = [{ name: "Status quo", color: "--series-2", wash: "--series-2-wash", data: b.fan }];
    if (body.policy !== "P0") series.push({ name: POLICY_LABEL[a.policy] || a.policy, color: "--series-1", wash: "--series-1-wash", data: a.fan });
    legend($("#sim-legend"), series.slice().reverse().map((s) => ({ label: s.name, color: s.color })));
    fanChart($("#sim-fan"), series);
    const shock = body.shock_days > 0 ? `${body.country === "RU" ? "Russian" : "French"} supply disrupted days ${body.shock_start}–${body.shock_start + body.shock_days}` : "no disruption";
    $("#sim-summary").innerHTML = `${esc(shock)} · ${a.seeds} futures each · ${esc(POLICY_LABEL[a.policy] || a.policy)}: <b>${pct(a.mean)}</b>
      (worst 10%: ${pct(a.crar10)}) vs status quo <b>${pct(b.mean)}</b> (worst 10%: ${pct(b.crar10)}).`;
    $("#sim-status").textContent = `Done in ${(a.runtime_s + b.runtime_s).toFixed(1)} s of simulation.`;
  } catch (e) {
    $("#sim-status").textContent = "Error: " + e.message;
  } finally { btn.disabled = false; }
}

// ------------------------------------------------------------ shell
function selectTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
  renderAll();
}
function renderAll() {
  const active = document.querySelector(".tabs button[aria-selected='true']").dataset.tab;
  ({ readiness: renderReadiness, opportunities: renderOpportunities, agencies: renderAgencies, signals: renderSignals,
     indigenisation: renderIndigenisation, ledger: renderLedger })[active]();
}

async function init() {
  try {
    [S.report, S.ledger] = await Promise.all([api("/api/report"), api("/api/ledger")]);
  } catch (e) {
    document.querySelector("main").innerHTML = `<div class="card">Could not load results: ${esc(e.message)}. Run <code>python -m nirantar demo</code> first.</div>`;
    return;
  }
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    S.scen = b.dataset.scen;
    document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    renderReadiness();
  }));
  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
  });
  $("#sim-form").addEventListener("submit", runSim);
  $("#verify-btn").addEventListener("click", verifyLedger);
  $("#tamper-btn").addEventListener("click", tamperDemo);
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderAll, 150); });
  renderReadiness();
}
init();
