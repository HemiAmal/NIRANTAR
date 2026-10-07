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
const ME = { mode: "demo", roles: [], permissions: [] };
const can = (p) => ME.mode !== "secure" || ME.permissions.includes(p);
async function api(path, body) {
  const headers = { "X-Nirantar": "1" };
  const opts = body ? { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) } : { headers };
  const r = await fetch(path, opts);
  const j = await r.json();
  if (r.status === 401 && path !== "/api/me" && path !== "/api/login") showLogin();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function showLogin(msg) {
  $("#login").hidden = false;
  $("#login-error").textContent = msg || "";
  $("#login-user").focus();
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
  const months = Math.round(maxDay / 30.4), narrow = W < 600,
    stepMo = months <= 4 ? 1 : narrow ? (months > 12 ? 6 : 3) : (months > 12 ? 4 : 2);
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

async function renderAccess() {
  const card = $("#access-card");
  card.hidden = !(ME.mode === "secure" && ME.permissions.includes("admin"));
  if (card.hidden) return;
  try {
    const [u, a] = await Promise.all([api("/api/admin/users"), api("/api/admin/audit")]);
    $("#access-users").innerHTML = `<table><thead><tr><th>User</th><th>Roles</th><th>Signs as</th><th>Status</th></tr></thead><tbody>` +
      u.users.map((x) => `<tr><td>${esc(x.display)} <span class="muted">(${esc(x.username)})</span></td><td>${esc(x.roles.join(", "))}</td>
        <td><code>${esc(x.actor)}</code></td><td>${x.disabled ? "Disabled" : x.locked ? "Locked" : "Active"}</td></tr>`).join("") + "</tbody></table>";
    $("#access-audit").innerHTML = `<table><thead><tr><th>Time</th><th>User</th><th>Event</th><th>Detail</th><th>From</th></tr></thead><tbody>` +
      a.audit.slice(0, 40).map((x) => `<tr><td>${new Date(x.ts * 1000).toLocaleString()}</td><td>${esc(x.username || "")}</td>
        <td>${esc(x.event)}</td><td>${esc(x.detail || "")}</td><td>${esc(x.ip || "")}</td></tr>`).join("") + "</tbody></table>";
  } catch (e) { $("#access-users").textContent = "Could not load accounts: " + e.message; }
}

function renderLedger() {
  renderAccess();
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
        : e.kind === "snag_entry" ? `${p.tail} ${p.part}${p.position ? " pos " + p.position : ""}: ${nice(p.mode)}, ${nice(p.action)} (${p.input}${p.lang ? ", " + p.lang : ""})`
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

// ------------------------------------------------------------ CHANAKYA decision desk
const DK = { view: null, base: "All", poll: null, outcome: null, clock: null };
const REASON_LABEL = {
  MRV_CI_POSITIVE: "Approve: value clearly positive", OPERATIONAL_NEED: "Approve: operational need",
  AWAITING_FUNDS: "Defer: awaiting funds", NEED_MORE_INFO: "Defer: need more information", TRANSPORT_UNAVAILABLE: "Defer: no transport",
  OPERATIONAL_REASON: "Reject: operational reason", DATA_DOUBT: "Reject: doubt the data", SAFETY_CONCERN: "Reject: safety concern",
  DONOR_NEEDED_ELSEWHERE: "Reject: donor needed elsewhere",
};
const VERDICT_WORD = { accept: ["good", "Approved"], defer: ["warning", "Deferred"], reject: ["critical", "Rejected"] };
const storeGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const storeSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

async function loadPlan() {
  DK.view = await api("/api/plan");
  const st = DK.view.state;
  if (st.status === "building") {
    const pctDone = Math.round(((st.i || 0) / 4) * 100);
    $("#plan-status").innerHTML = `Preparing the plan: ${esc(st.step)}…<div class="progress"><i style="width:${pctDone}%"></i></div>`;
    $("#replan-btn").disabled = true;
    clearTimeout(DK.poll); DK.poll = setTimeout(loadPlan, 1000);
  } else {
    $("#replan-btn").disabled = !can("plan");
    if (st.status === "error") $("#plan-status").textContent = "Planning failed: " + st.error;
  }
  renderClock();
  if (DK.view.plan) renderDesk();
  else if (st.status !== "building") $("#plan-status").textContent = "No plan yet. Press “Re-plan now” (about 20–60 s).";
}

function canDecide(item, role) {
  if (!role) return false;
  return item.authority.includes(role) || item.authority.includes(role.split(" ")[0]);
}

function renderDesk() {
  const v = DK.view, P = v.plan, brd = P.board, base = DK.base;
  const inBase = (b) => base === "All" || b === base;
  if (v.state.status !== "building") {
    const scen = (P.scenario || []).map((f) => `${f[0]} supply disrupted to day ${(P.day || 0) + f[3]}`).join(", ");
    $("#plan-status").textContent = `${P.plan_id} · plan for ${P.day ? "day " + P.day : "today (day 0)"}${scen ? " under declared disruption (" + scen + ")" : ""} · prepared ${new Date(P.created * 1000).toLocaleString()} · ` +
      `${P.n_candidates} candidate actions priced on ${P.seeds} paired futures over ${P.horizon_days} days against today's procedures.`;
  }
  // tiles
  const tails = brd.tails, down = tails.filter((t) => t.status === "NMCS").length, maint = tails.filter((t) => t.status === "NMCM").length;
  const j = P.joint || {}, s = v.summary;
  $("#desk-tiles").innerHTML = [
    tile({ label: "Aircraft waiting for parts now", value: `${down}<span class="muted" style="font-size:16px"> / ${tails.length}</span>`,
      delta: `${maint} more in maintenance` }),
    tile({ label: `Plan value, next ${P.horizon_days} days`, value: j.mrv != null ? signed(j.mrv) : "–", hero: false,
      delta: j.mrv != null ? `weighted aircraft-days · 95% CI ${fmt(j.ci95[0])}–${fmt(j.ci95[1])} · availability ${pct(j.availability_today_procedures)} → ${pct(j.availability_with_plan)}` : "", up: j.mrv > 0 }),
    tile({ label: "Plan cost", value: `₹${fmt(P.cost_lakh, 1)} lakh`, delta: `${P.items.length} actions · budget ₹${fmt(P.budget_lakh)} lakh` }),
    tile({ label: "Awaiting a decision", value: fmt(s.pending), delta: s.pending ? `waiting costs ≈${fmt(s.pending_cod_per_day, 1)} aircraft-days per day` : `${s.approved} approved · ${s.rejected} rejected` }),
  ].join("");

  // base selector
  const bases = ["All", ...new Set(tails.map((t) => t.base))].sort((a, b) => (a === "All" ? -1 : b === "All" ? 1 : a.localeCompare(b)));
  $("#base-seg").innerHTML = bases.map((b) => `<button role="radio" aria-checked="${b === base}" data-base="${esc(b)}">${b === "All" ? "All bases" : esc(b)}</button>`).join("");
  $("#base-seg").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { DK.base = b.dataset.base; renderDesk(); renderClock(); }));

  // fleet status per base
  const groups = {};
  for (const t of tails) if (inBase(t.base)) {
    const k = t.base + "|" + t.fleet; groups[k] = groups[k] || { base: t.base, fleet: t.fleet, MC: 0, NMCM: 0, NMCS: 0 }; groups[k][t.status]++;
  }
  const FLEET = { FighterH: "Heavy fighter", HeloU: "Utility helicopter" };
  $("#fleet-status").innerHTML = `<table><thead><tr><th>Base</th><th>Fleet</th><th class="num">Ready</th><th class="num">In maintenance</th>
    <th class="num">Waiting for parts</th><th class="num">Available now</th></tr></thead><tbody>` +
    Object.values(groups).sort((a, b) => (a.base + a.fleet).localeCompare(b.base + b.fleet)).map((g) => {
      const n = g.MC + g.NMCM + g.NMCS;
      return `<tr><td>${esc(g.base)}</td><td>${esc(FLEET[g.fleet] || g.fleet)}</td><td class="num">${g.MC}</td><td class="num">${g.NMCM}</td>
        <td class="num">${g.NMCS}</td><td class="num">${pct(g.MC / n, 0)}</td></tr>`;
    }).join("") + "</tbody></table>";

  // AOG table with the plan's fix for each aircraft
  const fixFor = (t, w) => P.items.filter((it) => (it.kind === "cann" && it.tail === t.id) ||
    (it.kind !== "cann" && it.base === t.base && it.pn === w.pn));
  const aog = tails.filter((t) => t.status === "NMCS" && inBase(t.base))
    .flatMap((t) => t.waiting.map((w) => ({ t, w }))).sort((a, b) => b.w.days - a.w.days);
  $("#aog-table").innerHTML = aog.length ? `<table><thead><tr><th>Aircraft</th><th>Waiting for</th><th class="num">Waited</th>
    <th>Expected back without action</th><th>In today's plan</th></tr></thead><tbody>` + aog.map(({ t, w }) => {
      const fixes = fixFor(t, w);
      const grouped = {};
      for (const it of fixes) {
        const d = it.decision, key = it.kind_label + "|" + (d ? d.verdict : "");
        grouped[key] = (grouped[key] || 0) + 1;
      }
      const fixTxt = fixes.length ? Object.entries(grouped).map(([key, n]) => {
        const [label, verdict] = key.split("|"), st = verdict ? VERDICT_WORD[verdict] : null;
        return `<div>${esc(label)}${n > 1 ? ` ×${n}` : ""}${st ? " " + badge(st[0], st[1]) : ""}</div>`;
      }).join("") : `<span class="muted">–</span>`;
      return `<tr><td>${esc(t.id)}</td><td>${esc(w.name)}${w.pos ? " · pos " + w.pos : ""}</td><td class="num">${w.days < 1 ? "<1" : fmt(w.days)} d</td>
        <td>${w.eta != null ? `${w.eta < 1 ? "<1" : "~" + fmt(w.eta)} d <span class="small">(${esc(w.eta_source)})</span>` : `<span class="small">${esc(w.eta_source)}</span>`}</td>
        <td>${fixTxt}</td></tr>`;
    }).join("") + "</tbody></table>" : `<p class="muted">No aircraft waiting for parts${base === "All" ? "" : " at " + esc(base)}.</p>`;

  // 7-day risk
  const risky = tails.filter((t) => t.status === "MC" && inBase(t.base)).sort((a, b) => b.risk7 - a.risk7).slice(0, 8);
  if (risky.length) hBars($("#risk-bars"), risky.map((t) => ({ label: `${t.id} · ${t.risk_part}`, value: t.risk7 * 100 })),
    { unit: "%", digits: 0, tipFn: (r) => `<div class="t">${esc(r.label)}</div>Chance of a new failure within 7 days: <b>${fmt(r.value)}%</b>` });
  else $("#risk-bars").innerHTML = `<p class="muted">No serviceable aircraft here.</p>`;

  // plan table
  const role = $("#role").value;
  const items = P.items.map((it, i) => ({ ...it, n: i + 1 })).filter((it) => inBase(it.base));
  $("#plan-hint").textContent = `Ranked by value. Value = change in weighted aircraft-available-days over ${P.horizon_days} days vs today's procedures; ` +
    `the plan's joint value (${j.mrv != null ? signed(j.mrv) : "–"}) is below the sum of its parts (${j.sum_of_parts != null ? signed(j.sum_of_parts) : "–"}) because actions overlap.`;
  const reasonOpts = Object.entries(v.reasons).map(([verdict, codes]) => codes.map((c) => `<option value="${verdict}|${c}">${esc(REASON_LABEL[c] || c)}</option>`).join("")).join("");
  $("#plan-table").innerHTML = items.length ? `<table class="plan"><thead><tr><th class="num">#</th><th>Action and why</th><th class="num">Value (wAAD)</th>
    <th class="num">Cost (₹ lakh)</th><th class="num">Delay cost / day</th><th>Evidence · approver</th><th>Decision</th></tr></thead><tbody>` +
    items.map((it) => {
      const [lvl, txt] = GRADE[it.grade] || ["neutral", it.grade];
      const d = it.decision;
      let cell;
      if (v.state.status === "building" && !(d && d.verdict !== "defer")) {
        cell = `<div class="needs">Re-planning… decide on the new plan</div>`;
      } else if (d && d.verdict !== "defer") {
        const [l, w] = VERDICT_WORD[d.verdict];
        cell = `${badge(l, w)}<div class="small">${esc(d.role || "")} · ${esc(REASON_LABEL[d.reason_code] || d.reason_code)} · #${d.seq}</div>`;
      } else if (!canDecide(it, role)) {
        cell = `${d ? badge("warning", "Deferred") : ""}<div class="needs">Needs ${esc(it.authority)}</div>`;
      } else {
        cell = `${d ? badge("warning", "Deferred") : ""}<div class="sign" data-seq="${it.ledger_seq}">
          <select aria-label="Decision for action ${it.n}"><option value="">Choose…</option>${reasonOpts}</select><button type="button">Sign</button></div>`;
      }
      const cod = it.cod_per_day != null ? (it.cod_per_day < 0.1 ? "≈0" : fmt(it.cod_per_day, 1)) : "–";
      return `<tr><td class="num">${it.n}</td>
        <td class="act"><span class="kind">${esc(it.kind_label)}</span><div class="act-text">${esc(it.text)}</div>
          <div class="small">${esc(it.reason)}</div>
          <details class="why"><summary>What the simulation shows</summary><div class="small">${esc(it.explanation)}</div></details></td>
        <td class="num"><b>${signed(it.mrv, 1)}</b><div class="small">CI ${fmt(it.ci95[0], 1)} to ${fmt(it.ci95[1], 1)}</div>
          <div class="small">helps in ${Math.round(it.p_positive * 100)}% of futures</div></td>
        <td class="num">${fmt(it.cost_lakh, 1)}</td><td class="num">${cod}</td>
        <td>${badge(lvl, "Data " + txt)}<div class="small" style="margin-top:4px">${esc(it.authority)}</div></td><td>${cell}</td></tr>`;
    }).join("") + "</tbody></table>" : `<p class="muted">No plan actions${base === "All" ? "" : " for " + esc(base)}.</p>`;
  $("#plan-table").querySelectorAll(".sign button").forEach((b) => b.addEventListener("click", async () => {
    const box = b.parentElement, val = box.querySelector("select").value;
    if (!val) { toast("Choose a decision and reason first"); return; }
    const [verdict, reason] = val.split("|");
    b.disabled = true;
    try {
      const r = await api("/api/decision", { ledger_seq: +box.dataset.seq, verdict, reason_code: reason, role: $("#role").value });
      toast(`${VERDICT_WORD[verdict][1]}: signed into the ledger as entry #${r.seq}`);
      S.ledger = await api("/api/ledger");
      await loadPlan();
    } catch (e) { toast("Not signed: " + e.message); b.disabled = false; }
  }));

  // not selected
  const ns = P.not_selected.filter((it) => inBase(it.base));
  $("#ns-summary").textContent = `Considered but not selected (${ns.length})`;
  $("#ns-table").innerHTML = `<table><thead><tr><th>Action</th><th class="num">Value</th><th class="num">95% CI</th><th class="num">Futures it helps</th><th>Why not</th></tr></thead><tbody>` +
    ns.map((it) => `<tr><td><span class="kind">${esc(it.kind_label)}</span><div>${esc(it.text)}</div></td><td class="num">${signed(it.mrv, 1)}</td>
      <td class="num">${fmt(it.ci95[0], 1)} to ${fmt(it.ci95[1], 1)}</td><td class="num">${Math.round(it.p_positive * 100)}%</td><td>${esc(it.not_selected)}</td></tr>`).join("") +
    "</tbody></table>";
  if (DK.outcome) renderOutcome();
}

async function runOutcome(which) {
  const btns = [$("#outcome-btn"), $("#outcome-all-btn")];
  btns.forEach((b) => (b.disabled = true));
  $("#outcome-summary").textContent = "Simulating…";
  try {
    DK.outcome = await api("/api/plan/outcome", { which });
    renderOutcome();
  } catch (e) { $("#outcome-summary").textContent = "Error: " + e.message; }
  finally { btns.forEach((b) => (b.disabled = false)); }
}
function renderOutcome() {
  const o = DK.outcome;
  const label = o.which === "all" ? "With the whole plan" : "With approved actions";
  const series = [{ name: "Today's procedures", color: "--series-2", wash: "--series-2-wash", data: o.fan_base },
    { name: label, color: "--series-1", wash: "--series-1-wash", data: o.fan_plan }];
  legend($("#outcome-legend"), series.slice().reverse().map((x) => ({ label: x.name, color: x.color })));
  fanChart($("#outcome-fan"), series);
  $("#outcome-summary").innerHTML = o.n_actions === 0 ? "No actions approved yet: both lines are today's procedures. Approve actions above, or simulate the whole plan."
    : `${o.n_actions} action${o.n_actions > 1 ? "s" : ""} · ${o.seeds} paired futures: mean availability <b>${pct(o.availability_plan)}</b> vs <b>${pct(o.availability_base)}</b>
      with today's procedures; <b>${signed(o.waad_gain)}</b> weighted aircraft-days and <b>${fmt(o.nmcs_days_saved)}</b> fewer aircraft-days waiting for parts.`;
}

async function renderDeskTab() {
  if (!DK.view) {
    const roleSel = $("#role");
    try {
      await loadPlan();
    } catch (e) { $("#plan-status").textContent = "Could not load the plan: " + e.message; return; }
    const roles = ME.mode === "secure" ? DK.view.roles.filter((r) => ME.roles.includes(r)) : DK.view.roles;
    roleSel.innerHTML = roles.length ? roles.map((r) => `<option>${esc(r)}</option>`).join("") : `<option value="">View only</option>`;
    roleSel.disabled = roles.length < 2;
    roleSel.value = roles.includes(storeGet("nirantar-role", "")) ? storeGet("nirantar-role", "") : (roles[0] || "");
    roleSel.addEventListener("change", () => { storeSet("nirantar-role", roleSel.value); if (DK.view.plan) renderDesk(); });
    $("#replan-btn").addEventListener("click", async () => {
      try { await api("/api/plan/build", {}); DK.outcome = null; $("#outcome-fan").innerHTML = ""; $("#outcome-legend").innerHTML = ""; $("#outcome-summary").textContent = ""; loadPlan(); }
      catch (e) { toast(e.message); }
    });
    $("#outcome-btn").addEventListener("click", () => runOutcome("approved"));
    $("#adv1").addEventListener("click", () => advanceClock(1));
    $("#adv7").addEventListener("click", () => advanceClock(7));
    $("#clock-reset").addEventListener("click", resetClock);
    $("#shock-btn").addEventListener("click", declareShock);
    loadClock().catch((e) => toast("Clock: " + e.message));
    $("#outcome-all-btn").addEventListener("click", () => runOutcome("all"));
    if (DK.view.plan) renderDesk();
  } else {
    if (DK.view.plan) renderDesk();
    renderClock();
  }
}

// ------------------------------------------------------------ operations clock
const EVENT_KIND = { shock: ["critical", "Supply disruption"], applied: ["neutral", "Decision applied"], failure: ["serious", "Failure"],
  waiting: ["warning", "Waiting for parts"], restored: ["good", "Back on the line"] };

function lineChart(container, series, { yFmt = (v) => pct(v, 0), bands = [] } = {}) {
  const W = Math.max(container.clientWidth, 320), H = 260, m = { l: 46, r: 16, t: 12, b: 30 };
  const s = svgRoot(container, W, H);
  const xs = series[0].points.map((p) => p[0]), maxX = Math.max(...xs), minX = Math.min(0, ...xs);
  const ys = series.flatMap((x) => x.points.map((p) => p[1]));
  const lo = Math.max(0, Math.floor((Math.min(...ys) - 0.03) * 20) / 20), hi = Math.min(1, Math.ceil((Math.max(...ys) + 0.03) * 20) / 20);
  const X = (d) => m.l + ((d - minX) / Math.max(maxX - minX, 1)) * (W - m.l - m.r);
  const Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  for (const t of niceTicks(lo, hi, 4)) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grid" }, s);
    el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, s).textContent = yFmt(t);
  }
  for (const [b0, b1, label] of bands) {          // shaded periods, e.g. a declared supply disruption
    const x0 = X(Math.max(b0, minX)), x1 = X(Math.min(b1, maxX));
    if (x1 <= x0) continue;
    el("rect", { x: x0, y: m.t, width: x1 - x0, height: H - m.t - m.b, class: "band" }, s);
    el("text", { x: x0 + 6, y: m.t + 12, class: "band-label" }, s).textContent = label;
  }
  for (const t of niceTicks(lo, hi, 4)) el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grid" }, s);
  el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis" }, s);
  for (const t of niceTicks(minX, maxX, W < 600 ? 4 : 8).filter((t) => Number.isInteger(t))) {
    el("text", { x: X(t), y: H - m.b + 18, "text-anchor": t === minX ? "start" : t === maxX ? "end" : "middle" }, s).textContent = t === 0 ? "Today" : `Day ${t}`;
  }
  for (const ser of series) {
    const pts = ser.points;
    if (pts.length > 1) el("path", { d: "M" + pts.map((p) => `${X(p[0])},${Y(p[1])}`).join(" L"),
      style: `fill:none;stroke:var(${ser.color});stroke-width:2;stroke-linejoin:round;stroke-linecap:round` }, s);
    const last = pts[pts.length - 1];
    el("circle", { cx: X(last[0]), cy: Y(last[1]), r: 4, style: `fill:var(${ser.color});stroke:var(--surface-1);stroke-width:2` }, s);
  }
  const cross = el("line", { y1: m.t, y2: H - m.b, class: "axis", visibility: "hidden" }, s);
  const dots = series.map((ser) => el("circle", { r: 4, visibility: "hidden", style: `fill:var(${ser.color});stroke:var(--surface-1);stroke-width:2` }, s));
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, s);
  hit.addEventListener("mousemove", (ev) => {
    const box = s.getBoundingClientRect(), x = (ev.clientX - box.left) * (W / box.width);
    const d = minX + ((x - m.l) / (W - m.l - m.r)) * (maxX - minX);
    let i = 0; for (let k = 0; k < xs.length; k++) if (Math.abs(xs[k] - d) < Math.abs(xs[i] - d)) i = k;
    cross.setAttribute("x1", X(xs[i])); cross.setAttribute("x2", X(xs[i])); cross.setAttribute("visibility", "visible");
    series.forEach((ser, j) => { dots[j].setAttribute("cx", X(ser.points[i][0])); dots[j].setAttribute("cy", Y(ser.points[i][1])); dots[j].setAttribute("visibility", "visible"); });
    const diff = series.length === 2 ? series[0].points[i][1] - series[1].points[i][1] : null;
    showTip(`<div class="t">Day ${xs[i]}</div>` + series.map((ser) => `<div class="r"><span><i style="background:var(${ser.color})"></i>${esc(ser.name)}</span><b>${yFmt(ser.points[i][1])}</b></div>`).join("") +
      (diff != null ? `<div class="r muted"><span>Difference</span><span>${pts(diff)}</span></div>` : ""), ev.clientX, ev.clientY);
  });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); });
}

async function loadClock() {
  DK.clock = await api("/api/clock");
  renderClock();
}
function renderClock() {
  const c = DK.clock;
  if (!c) return;
  $("#clock-title").textContent = c.day === 0 ? "Operations clock · today (day 0)" : `Operations clock · day ${c.day}`;
  const nApplied = c.applied.length;
  $("#clock-tiles").innerHTML = [
    tile({ label: "Gained by approved decisions", value: c.log.length ? signed(c.waad_gained) : "–",
      delta: c.log.length ? `weighted aircraft-days vs the shadow fleet (${signed(c.aircraft_days_gained)} aircraft-days)` : "advance the clock to measure", up: c.waad_gained > 0 }),
    tile({ label: "Available now", value: c.availability_live != null ? pct(c.availability_live, 0) : "–",
      delta: c.availability_shadow != null ? `shadow fleet: ${pct(c.availability_shadow, 0)}` : "" }),
    tile({ label: "Waiting for parts now", value: fmt(c.waiting_live), delta: `shadow fleet: ${fmt(c.waiting_shadow)}` }),
    tile({ label: "Decisions applied", value: fmt(nApplied), delta: nApplied ? `latest on day ${c.applied[0].day}` : "approve plan actions, then advance" }),
  ].join("");
  if (c.log.length) {
    const series = [{ name: "With approved decisions", color: "--series-1", points: c.log.map((r) => [r.day, r.live]) },
      { name: "Shadow fleet (no decisions)", color: "--series-2", points: c.log.map((r) => [r.day, r.shadow]) }];
    legend($("#clock-legend"), series.map((x) => ({ label: x.name, color: x.color })));
    const SUP = { RU: "Russian", FR: "French" };
    const bands = (c.shocks || []).map((sh) => [sh.start, sh.end, `${SUP[sh.country] || sh.country} supply disrupted`]);
    lineChart($("#clock-chart"), series, { bands });
  } else {
    $("#clock-legend").innerHTML = "";
    $("#clock-chart").innerHTML = `<p class="muted">Approve some of today's actions, then advance the clock.</p>`;
  }
  const evs = c.events.filter((e) => DK.base === "All" || !e.base || e.base === DK.base);
  const SUPN = { RU: "Russian", FR: "French" };
  const active = (c.shocks || []).filter((sh) => sh.active);
  const regimeTxt = Object.entries(c.regimes || {}).filter(([, st]) => st !== "normal").map(([k, st]) => `${SUPN[k] || k} supply ${st}`);
  $("#shock-status").innerHTML = active.map((sh) => badge("critical", `${SUPN[sh.country] || sh.country} supply disrupted to day ${sh.end}`)).join("") +
    (active.length ? "" : regimeTxt.map((t) => badge("warning", t)).join(""));
  $("#shock-btn").disabled = DK.view?.state?.status === "building" || !can("clock");
  $("#clock-events").innerHTML = evs.length ? evs.map((e) => {
    const [lvl, word] = EVENT_KIND[e.kind] || ["neutral", e.kind];
    return `<li><span class="d">Day ${e.day}</span><span>${badge(lvl, word)}</span><span>${esc(e.text)}</span></li>`;
  }).join("") : `<li><span class="muted">No events yet.</span></li>`;
  $("#clock-log").querySelector("summary").textContent = c.events_total > c.events.length
    ? `Station log (latest ${evs.length} of ${c.events_total} events)` : `Station log (${evs.length} events)`;
  for (const id of ["#adv1", "#adv7"]) $(id).disabled = DK.view?.state?.status === "building" || !can("clock");
}
async function advanceClock(days) {
  for (const id of ["#adv1", "#adv7", "#clock-reset"]) $(id).disabled = true;
  try {
    const before = DK.clock ? DK.clock.applied.length : 0;
    DK.clock = await api("/api/clock/advance", { days });
    const applied = DK.clock.applied.length - before;
    toast(`Day ${DK.clock.day}: ${applied ? applied + " approved action" + (applied > 1 ? "s" : "") + " applied, " : ""}a new plan is being prepared`);
    DK.outcome = null; $("#outcome-fan").innerHTML = ""; $("#outcome-legend").innerHTML = ""; $("#outcome-summary").textContent = "";
    S.ledger = await api("/api/ledger");
    renderClock();
    await loadPlan();
  } catch (e) { toast("Not advanced: " + e.message); }
  finally { $("#clock-reset").disabled = !can("clock"); renderClock(); }
}
async function declareShock() {
  $("#shock-btn").disabled = true;
  try {
    DK.clock = await api("/api/clock/disrupt", { country: $("#shock-country").value, days: +$("#shock-days").value });
    toast("Disruption declared and signed into the ledger; re-planning for the crisis");
    DK.outcome = null; $("#outcome-fan").innerHTML = ""; $("#outcome-summary").textContent = "";
    S.ledger = await api("/api/ledger");
    renderClock(); await loadPlan();
  } catch (e) { toast("Not declared: " + e.message); renderClock(); }
}
async function resetClock() {
  try {
    DK.clock = await api("/api/clock/reset", {});
    toast("Clock reset to day 0");
    DK.outcome = null; $("#outcome-fan").innerHTML = ""; $("#outcome-summary").textContent = "";
    renderClock(); await loadPlan();
  } catch (e) { toast("Not reset: " + e.message); }
}

// ------------------------------------------------------------ SAARTHI snag entry
const SN = { opts: null, fields: null, prov: {}, heard: {}, errors: {}, choices: {}, edited: new Set(), findings: [],
  t0: null, input: "typed", lang: "", transcript: "", res: null, timer: null, entries: null };
const EXAMPLES = [
  ["English", "FI B1 06, number one fuel pump pressure low, replaced"],
  ["Hinglish", "Fighter B1 ka saat number, do number engine pe oil pump, chip detector clean, pressure kam, oil sample bhej diya"],
  ["हिन्दी", "एफ आई बी वन जीरो सेवन, दूसरा हाइड्रोलिक पंप लीक, बदल दिया"],
  ["Fleet signal", "HE B4 02 hydraulic pump left side corrosion, inspected"],
  ["Wrong serial", "HE B3 02 starter generator number 1, serial 961, no output"],
  ["Ambiguous", "B1 05 pump leaking"],
];
const PROV = {
  heard: ["good", "Heard"], inferred: ["neutral", "Inferred"], ambiguous: ["warning", "Choose one"],
  missing: ["critical", "Needed"], edited: ["neutral", "Edited"], optional: ["neutral", "Optional"],
};
const STATUS_WORD = { good: "OK", info: "Note", warning: "Check", critical: "Blocking" };
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null;

function snStart(input) {
  if (SN.t0 == null) SN.t0 = performance.now();
  if (input) SN.input = input;
  if (!SN.timer) SN.timer = setInterval(() => {
    if (SN.t0 != null && !$("#snag-card").hidden) $("#snag-timer").textContent = `Time to log: ${Math.round((performance.now() - SN.t0) / 1000)} s`;
  }, 500);
}
function snReset() {
  Object.assign(SN, { fields: null, prov: {}, heard: {}, errors: {}, choices: {}, edited: new Set(), findings: [], t0: null,
    input: "typed", lang: "", transcript: "", res: null });
  $("#snag-text").value = "";
  $("#snag-card").hidden = true;
  $("#snag-timer").textContent = "";
}

async function snParse() {
  const text = $("#snag-text").value.trim();
  if (!text) { $("#snag-text").focus(); return; }
  snStart();
  $("#parse-btn").disabled = true;
  try {
    const r = await api("/api/saarthi/parse", { text });
    const d = r.draft;
    SN.transcript = text; SN.lang = d.lang; SN.findings = d.findings.concat(d.also_mentioned.map((x) => "Also mentioned: " + x));
    SN.edited = new Set();
    SN.prov = {}; SN.heard = {}; SN.errors = {}; SN.choices = {};
    for (const [k, f] of Object.entries(d.fields)) {
      SN.prov[k] = f.source; SN.heard[k] = f.heard; SN.errors[k] = f.error;
      if (f.source === "ambiguous") SN.choices[k] = f.options;
    }
    SN.fields = { ...r.fields };
    for (const k of r.inferred || []) SN.prov[k] = "inferred";
    if (SN.prov.position === "missing" && r.fields.position) SN.prov.position = "inferred";
    SN.res = r;
    $("#snag-card").hidden = false;
    renderSnag();
  } catch (e) { toast("Could not structure: " + e.message); }
  finally { $("#parse-btn").disabled = false; }
}

async function snRecheck() {
  try {
    const r = await api("/api/saarthi/check", { fields: SN.fields, findings: SN.findings });
    for (const k of r.inferred || []) if (!SN.edited.has(k)) SN.prov[k] = "inferred";
    SN.fields = { ...SN.fields, ...r.fields };
    SN.res = r;
    renderSnag();
  } catch (e) { toast(e.message); }
}

function snOnChange(key, value) {
  snStart();
  SN.fields[key] = value === "" ? null : key === "position" ? Number(value) : value;
  SN.edited.add(key); SN.prov[key] = "edited"; SN.errors[key] = ""; delete SN.choices[key];
  const part = SN.opts.parts.find((p) => p.pn === SN.fields.part);
  const tail = SN.opts.tails.find((t) => t.id === SN.fields.tail);
  if (key === "tail" && part && tail && part.fleet !== tail.fleet) { SN.fields.part = null; SN.fields.mode = null; SN.fields.position = null; SN.prov.part = "missing"; }
  if (key === "part") { SN.fields.position = part && part.positions === 1 ? 1 : null; SN.fields.mode = SN.fields.mode && part && SN.opts.modes[part.family].some((m) => m.id === SN.fields.mode) ? SN.fields.mode : null; }
  snRecheck();
}

function fieldBox(key, label, control, required = true) {
  const v = SN.fields[key];
  let p = SN.prov[key] || "missing";
  if (p === "missing" && (v != null && v !== "")) p = "inferred";
  if (p === "missing" && !required) p = "optional";
  const [lvl, word] = PROV[p];
  const need = required && (v == null || v === "");
  const heard = SN.errors[key] ? `<span class="heard" style="color:var(--critical)">${esc(SN.errors[key])}</span>`
    : SN.heard[key] && p !== "edited" ? `<span class="heard">heard: “${esc(SN.heard[key])}”</span>` : "";
  let opts = SN.choices[key];
  if (opts && key === "part") {
    const tail = SN.opts.tails.find((t) => t.id === SN.fields.tail);
    if (tail) opts = opts.filter((pn) => (SN.opts.parts.find((x) => x.pn === pn) || {}).fleet === tail.fleet);
  }
  const choices = opts && opts.length ? `<div class="chips">${opts.map((o) => `<button type="button" data-choose="${esc(key)}" data-val="${esc(o)}">${esc(choiceLabel(key, o))}</button>`).join("")}</div>` : "";
  return `<div class="sf${need ? " need" : ""}"><div class="sf-head"><label for="sf-${key}">${esc(label)}</label><span class="prov"><span class="ic ${lvl}" style="width:7px;height:7px;border-radius:50%;display:inline-block"></span>${word}</span></div>
    ${control}${heard}${choices}</div>`;
}
function choiceLabel(key, v) {
  if (key === "part") { const p = SN.opts.parts.find((x) => x.pn === v); return p ? `${p.name} (${p.pn})` : v; }
  return v;
}
function sel(key, opts, placeholder = "Choose…") {
  return `<select id="sf-${key}" data-field="${key}"><option value="">${esc(placeholder)}</option>${opts}</select>`;
}

function renderSnag() {
  const f = SN.fields, o = SN.opts;
  const tail = o.tails.find((t) => t.id === f.tail);
  const part = o.parts.find((p) => p.pn === f.part);
  const bases = [...new Set(o.tails.map((t) => t.base + "|" + t.fleet))];
  const tailOpts = bases.map((bf) => {
    const [b, fl] = bf.split("|");
    return `<optgroup label="${esc(b)} · ${esc(o.fleets[fl])}">${o.tails.filter((t) => t.base === b && t.fleet === fl)
      .map((t) => `<option value="${esc(t.id)}">${esc(t.id)}</option>`).join("")}</optgroup>`;
  }).join("");
  const partOpts = o.parts.filter((p) => !tail || p.fleet === tail.fleet).map((p) => `<option value="${esc(p.pn)}">${esc(p.pn)} · ${esc(p.name)}</option>`).join("");
  const posOpts = part ? Array.from({ length: part.positions }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("") : "";
  const modes = part ? o.modes[part.family] : Object.values(o.modes).flat().filter((m, i, a) => a.findIndex((x) => x.id === m.id) === i);
  const modeOpts = modes.map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join("");
  const actOpts = o.actions.map((a) => `<option value="${esc(a.id)}">${esc(a.label)}</option>`).join("");
  const onRecord = SN.res && SN.res.serial_on_record;
  $("#snag-fields").innerHTML = [
    fieldBox("tail", "Aircraft", sel("tail", tailOpts)),
    fieldBox("part", "Part", sel("part", partOpts)),
    fieldBox("position", "Position", sel("position", posOpts, part ? "Choose…" : "Pick a part first")),
    fieldBox("mode", "Finding", sel("mode", modeOpts)),
    fieldBox("action", "Action taken", sel("action", actOpts)),
    fieldBox("serial", "Serial number (data plate)", `<input id="sf-serial" data-field="serial" type="text" autocomplete="off" spellcheck="false"
      value="${f.serial ?? ""}" placeholder="${onRecord != null ? "records: " + onRecord : "optional"}">`, false),
  ].join("");
  for (const k of ["tail", "part", "position", "mode", "action"]) { const s = $("#sf-" + k); if (s) s.value = f[k] ?? ""; }
  $("#snag-fields").querySelectorAll("[data-field]").forEach((n) => n.addEventListener("change", () => snOnChange(n.dataset.field, n.value)));
  $("#snag-fields").querySelectorAll("[data-choose]").forEach((b) => b.addEventListener("click", () => snOnChange(b.dataset.choose, b.dataset.val)));

  $("#snag-findings").innerHTML = SN.findings.length ? `<ul class="findings">${SN.findings.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const r = SN.res;
  $("#readback").innerHTML = `<div><b>Read-back:</b> ${esc(r.readback.en)}</div><div class="rb-hi">${esc(r.readback.hinglish)}</div>`;
  const order = { critical: 0, warning: 1, info: 2, good: 3 };
  $("#snag-checks").innerHTML = r.checks.slice().sort((a, b) => order[a.status] - order[b.status]).map((c) =>
    `<li><span class="ic ${c.status}"></span><div><div class="ct">${esc(c.title)}<span class="cs">${STATUS_WORD[c.status]}</span></div>${c.detail ? `<div class="cd">${esc(c.detail)}</div>` : ""}</div></li>`).join("");
  const btn = $("#confirm-btn");
  btn.disabled = !r.ready || !can("snag");
  btn.title = r.ready ? "" : "Resolve the blocking items first";
}

async function snConfirm() {
  const secs = SN.t0 != null ? (performance.now() - SN.t0) / 1000 : null;
  $("#confirm-btn").disabled = true;
  try {
    const e = await api("/api/saarthi/confirm", { fields: SN.fields, findings: SN.findings, transcript: SN.transcript,
      lang: SN.lang, input: SN.input, entry_seconds: secs, edited_fields: [...SN.edited] });
    const swap = e.removed_serial != null ? ` · S/N ${e.removed_serial} out${e.installed_serial != null ? `, S/N ${e.installed_serial} fitted` : ""}` : "";
    toast(`Signed as ledger entry #${e.seq}${swap}`);
    snReset();
    S.ledger = await api("/api/ledger");
    await loadEntries();
  } catch (err) { toast("Not signed: " + err.message); $("#confirm-btn").disabled = false; }
}

async function loadEntries() {
  SN.entries = await api("/api/saarthi/entries");
  renderEntries();
}
function renderEntries() {
  if (!SN.entries) return;
  const { entries, stats } = SN.entries;
  const hf = stats.entries ? stats.hands_free / stats.entries : null;
  $("#snag-tiles").innerHTML = [
    tile({ label: "Snags signed", value: fmt(stats.entries), delta: `${fmt(stats.voice)} by voice` }),
    tile({ label: "Median time to log", value: stats.median_seconds != null ? fmt(stats.median_seconds) + " s" : "–",
      delta: "target under 30 s", up: stats.median_seconds != null && stats.median_seconds < 30 }),
    tile({ label: "Signed without manual correction", value: hf != null ? pct(hf, 0) : "–", delta: "fields left as SAARTHI heard them" }),
  ].join("");
  const MODE = Object.fromEntries(Object.values(SN.opts.modes).flat().map((m) => [m.id, m.label]));
  const ACT = Object.fromEntries(SN.opts.actions.map((a) => [a.id, a.label]));
  $("#snag-entries").innerHTML = entries.length ? `<table><thead><tr><th class="num">#</th><th>Time</th><th>Aircraft</th><th>Part</th><th>Finding</th><th>Action</th>
    <th>Units</th><th>Input</th><th class="num">Seconds</th><th>Hash</th></tr></thead><tbody>` + entries.map((e) => `<tr>
      <td class="num">${e.seq}</td><td>${new Date(e.ts * 1000).toLocaleTimeString()}</td><td>${esc(e.tail)}</td>
      <td>${esc(e.part)}${e.position ? " · pos " + e.position : ""}</td><td>${esc(MODE[e.mode] || e.mode)}</td><td>${esc(ACT[e.action] || e.action)}</td>
      <td>${e.removed_serial != null ? "out " + e.removed_serial : ""}${e.installed_serial != null ? ", in " + e.installed_serial : ""}</td>
      <td>${esc(e.input || "")}${e.lang ? " · " + esc(e.lang) : ""}</td><td class="num">${e.entry_seconds != null ? fmt(e.entry_seconds) : "–"}</td>
      <td><code>${esc(e.hash)}</code></td></tr>`).join("") + "</tbody></table>"
    : `<p class="muted">No snags signed yet. Speak or type one above.</p>`;
}

// voice input: the node's own recogniser when it has a speech model; browser speech (a cloud service) only in demo mode
const REC = { ctx: null, stream: null, node: null, chunks: [], t0: 0 };

async function recordStart() {
  REC.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  REC.ctx = new AudioContext({ sampleRate: 16000 });
  await REC.ctx.audioWorklet.addModule("/recorder-worklet.js");
  const src = REC.ctx.createMediaStreamSource(REC.stream);
  REC.node = new AudioWorkletNode(REC.ctx, "nirantar-recorder");
  REC.chunks = []; REC.t0 = performance.now();
  REC.node.port.onmessage = (ev) => REC.chunks.push(ev.data);
  src.connect(REC.node);
}

async function recordStop() {
  const rate = REC.ctx.sampleRate;
  REC.stream.getTracks().forEach((t) => t.stop());
  await REC.ctx.close();
  const n = REC.chunks.reduce((a, c) => a + c.length, 0), pcm = new Int16Array(n);
  let i = 0;
  for (const c of REC.chunks) for (const v of c) pcm[i++] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
  REC.ctx = REC.stream = REC.node = null;
  return { pcm, rate };
}

function micSetup() {
  const mic = $("#mic"), status = $("#mic-status"), asr = (SN.opts && SN.opts.asr) || { available: false };
  const setPressed = (on) => { mic.setAttribute("aria-pressed", String(on)); mic.setAttribute("aria-label", on ? "Stop voice input" : "Start voice input"); };
  if (asr.available) {
    const langs = Object.keys(asr.languages);
    status.textContent = `Tap the microphone, speak, tap again. Recognised on this node (${langs.join(", ")}).`;
    let recording = false;
    mic.addEventListener("click", async () => {
      if (!recording) {
        try { await recordStart(); } catch (e) { status.textContent = "Microphone unavailable: " + e.message; return; }
        recording = true; setPressed(true); snStart("voice"); status.textContent = "Listening… tap again to finish.";
        return;
      }
      recording = false; setPressed(false); status.textContent = "Recognising…";
      try {
        const { pcm, rate } = await recordStop();
        const want = $("#asr-lang").value.slice(0, 2), lang = langs.includes(want) ? want : langs[0];
        const r = await fetch(`/api/saarthi/transcribe?lang=${lang}`, { method: "POST", body: pcm.buffer,
          headers: { "X-Nirantar": "1", "Content-Type": `audio/l16; rate=${rate}` } });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        if (!j.text) { status.textContent = "Heard nothing clear. Try again closer to the mic, or type."; return; }
        $("#snag-text").value = j.text;
        const alt = j.chosen === "restricted" ? j.free_text : j.restricted_text;
        status.textContent = alt && alt !== j.text ? `Got it. The other reading was: “${alt}”` : "Got it.";
        SN.input = "voice"; snParse();
      } catch (e) { status.textContent = "Voice error: " + e.message + ". Type the snag instead."; }
    });
    return;
  }
  if (!SR || ME.mode === "secure") {
    mic.disabled = true;
    status.textContent = ME.mode === "secure" ? "Voice input needs a speech model on this node (ask the administrator). Typing works."
      : "Voice input needs Chrome or Edge. Typing works everywhere.";
    return;
  }
  status.textContent = "Tap the microphone and speak. (Demo: the browser's speech service is online; use the node's model on a closed network.)";
  mic.addEventListener("click", () => {
    if (recog) { recog.stop(); return; }
    recog = new SR();
    recog.lang = $("#asr-lang").value;
    recog.interimResults = true;
    recog.continuous = false;
    recog.maxAlternatives = 1;
    snStart("voice");
    let finalText = "";
    recog.onstart = () => { setPressed(true); status.textContent = "Listening…"; };
    recog.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (ev.results[i].isFinal) finalText += ev.results[i][0].transcript + " ";
        else interim += ev.results[i][0].transcript;
      }
      $("#snag-text").value = (finalText + interim).trim();
    };
    recog.onerror = (ev) => {
      status.textContent = ({ "not-allowed": "Microphone permission was refused.", "no-speech": "Heard nothing. Try again closer to the mic.",
        network: "Speech service unreachable (offline?). Type the snag instead.", "audio-capture": "No microphone found." })[ev.error] || "Voice error: " + ev.error;
    };
    recog.onend = () => {
      setPressed(false);
      recog = null;
      if (finalText.trim()) { status.textContent = "Got it."; SN.input = "voice"; snParse(); }
      else if (status.textContent === "Listening…") status.textContent = "Tap the microphone and speak.";
    };
    recog.start();
  });
}

function speakReadback() {
  if (!SN.res || !window.speechSynthesis) { toast("Read-back audio is not available in this browser"); return; }
  const u = new SpeechSynthesisUtterance(SN.res.readback.en);
  u.lang = "en-IN"; u.rate = 0.95;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

async function renderSaarthi() {
  if (!SN.opts) {
    try { SN.opts = await api("/api/saarthi/options"); }
    catch (e) { $("#snag-entries").innerHTML = `<p>Could not start SAARTHI: ${esc(e.message)}</p>`; return; }
    $("#examples").innerHTML = EXAMPLES.map(([k, t], i) => `<button type="button" data-ex="${i}" title="${esc(t)}">${esc(k)}</button>`).join("");
    $("#examples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      snReset(); snStart("typed"); $("#snag-text").value = EXAMPLES[+b.dataset.ex][1]; snParse();
    }));
    $("#parse-btn").addEventListener("click", snParse);
    $("#snag-text").addEventListener("keydown", (ev) => {
      snStart();
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); snParse(); }
    });
    $("#confirm-btn").addEventListener("click", snConfirm);
    $("#speak-btn").addEventListener("click", speakReadback);
    $("#clear-btn").addEventListener("click", snReset);
    micSetup();
    await loadEntries();
  } else loadEntries().catch(() => renderEntries());
}

// ------------------------------------------------------------ guided demo (Document 3 §13.3, 7 minutes)
const GD = { i: 0, t0: null, tick: null, busy: false };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
async function waitFor(fn, ms = 240000) {
  const t = Date.now();
  while (!fn()) { if (Date.now() - t > ms) throw new Error("timed out"); await sleep(300); }
}
function spot(sel) {
  document.querySelectorAll(".spot").forEach((n) => n.classList.remove("spot"));
  const n = sel && $(sel);
  if (n) { n.classList.add("spot"); n.scrollIntoView({ behavior: "smooth", block: "center" }); }
}
async function approveAllForDemo() {
  const v = DK.view;
  for (const it of v.plan.items) {
    if (it.decision && it.decision.verdict !== "defer") continue;
    const role = v.roles.find((r) => canDecide(it, r));
    if (!role) continue;
    await api("/api/decision", { ledger_seq: it.ledger_seq, verdict: "accept", reason_code: "MRV_CI_POSITIVE", role });
  }
  S.ledger = await api("/api/ledger");
  await loadPlan();
}
const planReady = () => DK.view && DK.view.state.status !== "building" && DK.view.plan;
const exp = (scen, pol) => S.report.experiment.find((e) => e.scenario === scen && e.policy === pol) || {};

const STEPS = [
  { title: "Before you start", at: null, tab: "readiness", label: "Reset the station to day 0",
    notes: () => ["Run this a minute before presenting. It resets the operations clock to the end of the records (day 0) and keeps today's plan.",
      "Close other tabs, set the browser zoom so the whole tile row fits, and pick light or dark with <b>Theme</b>.",
      "Every number in the console is from synthetic data (BHARAT-FLEET). Say so once, up front."],
    run: async () => {
      await api("/api/clock/reset", {});
      if (DK.view) { DK.outcome = null; await loadClock(); await loadPlan(); }      // the desk re-reads its state
      selectTab("readiness"); toast("Station reset to day 0");
    } },
  { title: "The problem in one chart", at: 0, tab: "readiness", spot: "#tiles", label: "Show the 12-month forecast",
    notes: () => { const p0 = exp("normal", "P0 Reactive"); return [
      `With today's procedures the force keeps about <b>${pct(p0.availability)}</b> of its aircraft available, against a 75% goal.`,
      `The shaded band is the spread over ${S.report.config.n_seeds} simulated futures: readiness is a <b>risk</b>, not a number.`,
      "Most of the gap is aircraft <b>waiting for parts</b>, not aircraft breaking. That is what NIRANTAR attacks."]; },
    run: async () => { selectTab("readiness"); $('#scen-seg button[data-scen="normal"]').click(); spot("#fan"); } },
  { title: "Morning huddle: today's board and plan", at: 45, tab: "desk", spot: "#desk-tiles", label: "Open the plan's top action",
    notes: () => { const P = DK.view?.plan, j = P?.joint || {}, it = P?.items?.[0];
      return [
        `<b>${DK.view ? P.board.tails.filter((t) => t.status === "NMCS").length : "–"} of 70</b> aircraft are waiting for parts this morning.`,
        P ? `The desk priced <b>${P.n_candidates}</b> possible actions and proposes <b>${P.items.length}</b> for <b>₹${fmt(P.cost_lakh, 1)} lakh</b>: worth <b>${signed(j.mrv)}</b> weighted aircraft-days over 90 days (95% CI ${fmt(j.ci95[0])}–${fmt(j.ci95[1])}).` : "Load the plan.",
        it ? `Top action: <b>${esc(it.text)}</b>. It names its approver (<b>${esc(it.authority)}</b>) and what a week's delay costs.` : "",
        "Open “What the simulation shows”: it lists which aircraft stop waiting and by how much."]; },
    run: async () => { selectTab("desk"); await waitFor(() => $("#plan-table .why")); $("#plan-table .why").open = true; spot("#plan-table tbody tr"); } },
  { title: "SAARTHI: a snag spoken in Hindi", at: 105, tab: "saarthi", spot: "#snag-card", label: "Speak (example) and sign",
    notes: () => ["A technician says the snag in Hindi, Hinglish or English. Use the microphone in Chrome or Edge, or the example button.",
      "Each field shows whether it was <b>heard</b> or <b>inferred</b>. It never invents a value; if unsure, it asks.",
      "The checks run against the records: wrong serial, rogue unit, fleet signal, spares on the shelf. Then it is <b>signed into the ledger</b>."],
    run: async () => {
      selectTab("saarthi"); await waitFor(() => $('#examples button[data-ex="2"]'));
      $('#examples button[data-ex="2"]').click(); await waitFor(() => !$("#snag-card").hidden && $("#snag-checks li"));
      spot("#snag-card"); await sleep(1800);
      if (!$("#confirm-btn").disabled) $("#confirm-btn").click();
    } },
  { title: "DRISHTI: a fleet signal from the records", at: 150, tab: "signals", spot: "#sig-tiles", label: "Show the signal table",
    notes: () => { const s = (S.report.drishti.table || []).find((r) => r.signal);
      return [s ? `Confirmed: <b>${nice(s.family)} ${nice(s.mode)}</b> in <b>${nice(s.env)}</b> bases, <b>${fmt(s.rate_ratio, 1)}×</b> the fleet rate per flight hour.` : "Confirmed signals appear here.",
        "Found the way drug-safety teams find side effects: disproportionate reports, confirmed against flight-hour exposure.",
        "Action: a targeted inspection for that context only, not the whole fleet."]; },
    run: async () => { selectTab("signals"); spot("#sig-table"); } },
  { title: "Approve and run a week", at: 195, tab: "desk", spot: "#clock-card", label: "Approve the plan, advance 7 days",
    notes: () => ["Each approver signs only what the Action Authority Matrix gives them; the server refuses anyone else.",
      "Advancing the clock applies the approved actions. A <b>shadow fleet</b> meets exactly the same failures and repair times but takes no decisions.",
      "The gap between the two lines is what the decisions bought, measured, not estimated."],
    run: async () => {
      selectTab("desk"); await waitFor(planReady);
      await approveAllForDemo(); await advanceClock(7); await waitFor(planReady); spot("#clock-card");
    } },
  { title: "Shock: Russian supply disrupted", at: 225, tab: "desk", spot: "#clock-card", label: "Declare a 120-day disruption",
    notes: () => { const P = DK.view?.plan, j = P?.joint || {}, top = P?.items?.[0];
      return ["Exercise control declares Russian shipping, customs and payments disrupted for 120 days. It is signed into the ledger.",
        P && P.scenario?.length ? `The desk re-plans for the crisis: <b>${P.items.length}</b> actions worth <b>${signed(j.mrv)}</b>, led by <b>${esc(top?.text || "")}</b>.` : "The desk re-plans for the crisis.",
        "Re-routing repairs to an Indian depot cuts a ~262-day repair loop to ~38 days. The card states the trade-off: those repairs are less durable."]; },
    run: async () => {
      selectTab("desk"); await waitFor(planReady);
      $("#shock-country").value = "RU"; $("#shock-days").value = "120";
      await declareShock(); await waitFor(planReady); renderGuide(); spot("#plan-table tbody tr");
    } },
  { title: "SUSHRUTA: repair quality, not just speed", at: 270, tab: "agencies", spot: "#ag-dots", label: "Show agency quality",
    notes: () => { const r = S.report.sushruta.rogues;
      return ["Each agency's repair effectiveness is estimated from maintenance records alone, with an interval, and checked against the hidden truth.",
        `Rogue units (serials that keep failing) are flagged with <b>${Math.round(r.precision * 100)}%</b> precision; they are quarantined from the aircraft-on-ground pool.`,
        "That is where the durability trade-off on the routing card comes from."]; },
    run: async () => { selectTab("agencies"); spot("#ag-dots"); } },
  { title: "The proof", at: 300, tab: "readiness", spot: "#policy-bars", label: "Show the policy comparison under shock",
    notes: () => { const a = exp("supply_shock", "P0 Reactive"), b = exp("supply_shock", "P3 NIRANTAR"), p1 = exp("supply_shock", "P1 Prediction-only");
      return [`Under a supply shock, NIRANTAR keeps <b>${pct(b.availability)}</b> available vs <b>${pct(a.availability)}</b> with today's procedures: <b>${signed(b.delta_waad_vs_P0)}</b> weighted aircraft-days, about <b>${fmt(b.fighter_sqe_equivalent, 2)}</b> fighter squadrons' worth.`,
        `Prediction alone <b>hurts</b> (${signed(p1.delta_waad_vs_P0)}): it pulls parts early without the logistics to back it. The value is in pricing and routing.`,
        DK.clock?.log?.length ? `On the clock today: <b>${signed(DK.clock.waad_gained)}</b> weighted aircraft-days gained over the shadow fleet.` : ""]; },
    run: async () => { selectTab("readiness"); $('#scen-seg button[data-scen="supply_shock"]').click(); spot("#policy-bars"); } },
  { title: "Trust: tamper with the record", at: 345, tab: "ledger", spot: "#verify-result", label: "Verify, then tamper",
    notes: () => ["Every snag, recommendation, decision, execution and scenario is a signed, hash-chained ledger entry.",
      "Ask someone in the room to pick an entry; the tamper demo edits a copy and verification catches it instantly. The real ledger stays intact.",
      "Evidence grade decides who may approve. NIRANTAR never grounds or releases an aircraft."],
    run: async () => { selectTab("ledger"); await verifyLedger(); await sleep(1200); await tamperDemo(); spot("#verify-result"); } },
  { title: "Close", at: 390, tab: null, label: null,
    notes: () => ["<b>“NIRANTAR doesn't predict failures. It prices readiness, continuously.”</b>",
      "Ask: a pilot on two bases and one BRD, in shadow mode first, with the Services' real records.",
      "Everything shown runs offline on one laptop, from open-source parts."], run: null },
];

function renderGuide() {
  const st = STEPS[GD.i];
  $("#guide-step").textContent = GD.i === 0 ? "Preparation" : `Step ${GD.i} / ${STEPS.length - 1}`;
  $("#guide-title").textContent = st.title;
  $("#guide-notes").innerHTML = st.notes().filter(Boolean).map((n) => `<li>${n}</li>`).join("");
  const doBtn = $("#guide-do");
  doBtn.hidden = !st.run; doBtn.textContent = GD.busy ? "Working…" : st.label || "Do it"; doBtn.disabled = GD.busy;
  $("#guide-back").disabled = GD.i === 0 || GD.busy; $("#guide-next").disabled = GD.i === STEPS.length - 1 || GD.busy;
  updateGuideClock();
}
function updateGuideClock() {
  const st = STEPS[GD.i], next = STEPS[GD.i + 1];
  if (st.at == null || GD.t0 == null) { $("#guide-clock").textContent = st.at == null ? "" : `target ${mmss(st.at)}`; return; }
  const el_ = (Date.now() - GD.t0) / 1000;
  const end = next && next.at != null ? next.at : 420;
  const over = el_ - end;
  $("#guide-clock").textContent = `${mmss(el_)} · slot ${mmss(st.at)}–${mmss(end)}${over > 0 ? ` · ${mmss(over)} over` : ""}`;
}
function goStep(i) {
  GD.i = Math.max(0, Math.min(STEPS.length - 1, i));
  if (GD.i >= 1 && GD.t0 == null) GD.t0 = Date.now();
  const st = STEPS[GD.i];
  if (st.tab) selectTab(st.tab);
  spot(st.spot);
  renderGuide();
  setTimeout(renderGuide, 1500);            // notes that quote the plan refresh once the tab has loaded it
}
async function doStep() {
  const st = STEPS[GD.i];
  if (!st.run || GD.busy) return;
  GD.busy = true; renderGuide();
  try { await st.run(); } catch (e) { toast("Demo step failed: " + e.message); }
  finally { GD.busy = false; renderGuide(); }
}
function guideSetup() {
  $("#demo-btn").addEventListener("click", () => {
    const g = $("#guide");
    g.hidden = !g.hidden;
    if (!g.hidden) { goStep(GD.i); clearInterval(GD.tick); GD.tick = setInterval(updateGuideClock, 1000); }
    else { clearInterval(GD.tick); spot(null); }
  });
  $("#guide-close").addEventListener("click", () => { $("#guide").hidden = true; clearInterval(GD.tick); spot(null); });
  $("#guide-mini").addEventListener("click", () => {
    const g = $("#guide"), mini = g.classList.toggle("mini");
    $("#guide-mini").textContent = mini ? "Notes" : "Minimise";
  });
  $("#guide-back").addEventListener("click", () => goStep(GD.i - 1));
  $("#guide-next").addEventListener("click", () => goStep(GD.i + 1));
  $("#guide-do").addEventListener("click", doStep);
  document.addEventListener("keydown", (ev) => {
    if ($("#guide").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) return;
    if (ev.key === "ArrowRight") goStep(GD.i + 1);
    else if (ev.key === "ArrowLeft") goStep(GD.i - 1);
    else if (ev.key.toLowerCase() === "d") doStep();
  });
}

// ------------------------------------------------------------ shell
function selectTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
  renderAll();
}
function renderAll() {
  const active = document.querySelector(".tabs button[aria-selected='true']").dataset.tab;
  ({ readiness: renderReadiness, desk: renderDeskTab, saarthi: renderSaarthi, opportunities: renderOpportunities, agencies: renderAgencies, signals: renderSignals,
     indigenisation: renderIndigenisation, ledger: renderLedger })[active]();
}

async function showSource() {
  try {
    const src = await api("/api/source");
    if (src.mode !== "records") return;
    const b = $(".topbar .banner");
    const synthetic = /synthetic/i.test(src.generator || "");
    b.textContent = `Planning from records as of ${(src.as_of || "").slice(0, 10)}${synthetic ? " · synthetic export, not IAF data" : ""}`;
    b.title = [`Store: ${src.store}`, ...(src.notes || [])].join("\n");
  } catch (e) { /* keep the default banner */ }
}

async function whoAmI() {
  try {
    Object.assign(ME, await api("/api/me"));
  } catch (e) {
    return false;                                   // 401: not signed in
  }
  if (ME.mode === "secure") {
    $("#user-chip").hidden = false;
    $("#user-chip").textContent = `${ME.display} · ${ME.roles.join(", ")}`;
    $("#user-chip").title = `Signs as ${ME.actor}`;
    $("#logout-btn").hidden = false;
    $("#demo-btn").hidden = true;                   // the guided demo acts in every role: demo mode only
    $("#tamper-btn").hidden = !ME.permissions.includes("admin");
    if (!ME.permissions.includes("clock"))             // exercise control only; the server enforces it too
      for (const id of ["#adv1", "#adv7", "#clock-reset", "#shock-btn"]) { $(id).disabled = true; $(id).title = "Exercise control only"; }
  }
  return true;
}

function loginSetup() {
  $("#login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/login", { username: $("#login-user").value, password: $("#login-pass").value });
      location.reload();
    } catch (e) { $("#login-pass").value = ""; showLogin(e.message); }
  });
  $("#logout-btn").addEventListener("click", async () => {
    try { await api("/api/logout", {}); } finally { location.reload(); }
  });
}

async function init() {
  loginSetup();
  if (!(await whoAmI())) { showLogin(); return; }
  try {
    [S.report, S.ledger] = await Promise.all([api("/api/report"), api("/api/ledger")]);
  } catch (e) {
    document.querySelector("main").innerHTML = `<div class="card">Could not load results: ${esc(e.message)}. Run <code>python -m nirantar demo</code> first.</div>`;
    return;
  }
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
  document.querySelectorAll("#scen-seg button").forEach((b) => b.addEventListener("click", () => {
    S.scen = b.dataset.scen;
    document.querySelectorAll("#scen-seg button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    renderReadiness();
  }));
  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
  });
  $("#sim-form").addEventListener("submit", runSim);
  guideSetup();
  showSource();
  $("#verify-btn").addEventListener("click", verifyLedger);
  $("#tamper-btn").addEventListener("click", tamperDemo);
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderAll, 150); });
  renderReadiness();
}
init();
