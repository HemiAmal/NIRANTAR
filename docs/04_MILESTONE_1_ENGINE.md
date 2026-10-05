# NIRANTAR — Milestone 1: The Engine Core

> **Status:** built, tested (52 tests passing), run end-to-end on synthetic data, with a web console.
> **Scope:** the computational heart of NIRANTAR as designed in `03_NIRANTAR_PROPOSED_SOLUTION.md`, without UI, connectors or speech (those are later milestones).
> **Data:** 100% synthetic (BHARAT-FLEET) with known ground truth. **No number here is an IAF result.** The numbers show the methods work and reveal honest trade-offs.

---

## 1. What was built

| Module | Package | What it does now | Doc 3 section |
|---|---|---|---|
| **BHARAT-FLEET** | `nirantar/bharat_fleet` | Synthetic world: 2 fleets (40 heavy fighters, 30 utility helicopters), 4 bases with environment classes, 16 part numbers, 5 repair agencies with hidden repair quality, Russian/French/Indian supply regimes, 3% rogue serials, environment-dependent failure modes | §12 |
| **SANJAYA** | `nirantar/sanjaya` | Event-driven sustainment digital twin: flying, Weibull + Kijima virtual-age failures, inspections, hard-time overhauls, base stores, backorders, repair queues with capacity, supply-regime shipping delays, policies, actions. Ensembles, fan charts, Readiness-at-Risk. **Slot-keyed common random numbers** make paired comparisons precise. ~0.05 s per aircraft-year-fleet run | §6.8 |
| **DHANVANTARI Tier C** | `nirantar/dhanvantari` | Records-only reliability: hierarchical Weibull with environment effects, Kijima type-I imperfect repair with **per-agency repair effectiveness q**, shared gamma frailty, MAP with **exact analytic gradients**, Laplace uncertainty, prediction intervals | §6.4 |
| **SUSHRUTA** | `nirantar/sushruta` | Agency scorecards (turnaround + q with CIs), **rogue-serial detection** (EM two-class mixture) | §6.5 |
| **DRISHTI** | `nirantar/drishti` | Airworthiness pharmacovigilance: PRR, ROR, BCPNN IC with Norén bounds, **exposure-normalised rate ratios** (removes compositional false alarms), signal and candidate tiers, time-to-signal | §6.6 |
| **SATYA** | `nirantar/satya` | 10 record invariants, data-quality scores, quarantine, defect injection with ground truth, **Evidence Grades E1–E5** | §6.2, §10.1 |
| **CHITRAGUPTA** | `nirantar/chitragupta` | Ed25519-signed, hash-chained, RFC 6962 Merkle ledger; signed tree heads; inclusion proofs; tamper detection; JSON-lines persistence | §6.3 |
| **CHANAKYA** | `nirantar/chanakya` | Paired-simulation **MRV** with CIs, counterfactual **trace-diff explanations**, **Cost-of-Delay**, analytic screening (Palm/EBO), budgeted greedy portfolio, status-quo consumption portfolio for comparison | §6.9, §6.10 |
| **VISHWAKARMA** | `nirantar/vishwakarma` | Indigenisation ranking by risk-weighted readiness per crore (normal + supply shock) | §6.11 |
| **Pipeline + CLI** | `nirantar/pipeline.py`, `python -m nirantar demo` | Runs everything end to end, writes `experiments/results/milestone1_report.{md,json}` and a signed `ledger.jsonl` | §13 |

---

## 2. How to run

```bash
python -m pip install -e ".[dev]"  # numpy, scipy, pandas, cryptography, pytest
python -m pytest -q                # all tests, ~20 s
python -m nirantar demo --quick    # ~15 s, fewer seeds
python -m nirantar demo            # full run, ~60 s -> experiments/results/
python -m nirantar serve           # web console on http://127.0.0.1:8050
```

### 2.1 The web console (Milestone 4a, built early for demos)

`python -m nirantar serve` opens a local, offline console (Python standard library + vanilla JS + hand-drawn SVG; no CDN, no cloud; light and dark modes; works on phones):

| Tab | What it shows |
|---|---|
| **Readiness room** | Headline availability (NIRANTAR vs status quo), aircraft-days recovered, worst-10% availability; 12-month forecast fan chart; value of every policy vs status quo with 95% CIs; **live what-if** that re-runs the digital twin with a supplier disruption you choose (≈0.5 s per 6 futures) |
| **Opportunities** | Priced actions with value, 95% CI, value certainty, data evidence grade, who decides and a counterfactual explanation; **Accept / Defer / Reject** buttons sign the decision into the ledger; cost of delay |
| **Repair agencies** | Repair-effectiveness *q* per agency with 90% intervals against the hidden synthetic truth; turnaround; rogue-unit detection precision/recall |
| **Fleet signals** | DRISHTI confirmed signals and review candidates, with IC, PRR and exposure rate ratios |
| **Indigenisation** | Parts ranked by readiness gained per crore under normal operations and a supply shock |
| **Data & ledger** | SATYA data-quality summary; full signed ledger; **Verify** (signatures, hash chain, Merkle tree head) and **Tamper demo** (edits a copy, shows detection, real ledger untouched) |

The API (`/api/report`, `/api/ledger`, `/api/decision`, `/api/simulate`, `/api/ledger/tamper-demo`) validates inputs, blocks path traversal and binds to localhost by default.

---

## 3. Results (full run: 5-year history, 365-day horizon, 20 paired seeds per arm)

### 3.1 Four-policy experiment

Policies (Doc 3 §13.2): **P0** reactive status quo · **P1** prediction-only (swap high-risk parts at inspection) · **P2** prediction + spares + scheduling (P1 + lateral transfers, need-based return, AOG priority) · **P3 NIRANTAR** (P2 + capacity/quality-aware routing + rogue quarantine + CHANAKYA portfolio). All arms get the same ₹6 crore spares budget: P0–P2 spend it the status-quo way (by last year's consumption), P3 spends it by CHANAKYA. Ablation rows add one NIRANTAR component at a time to P2.

Δ wAAD = change in role-weighted aircraft-available-days vs P0 on identical random streams (95% CI). CRaR10 = mean availability in the worst 10% of futures.

| Scenario | Policy | Availability | Δ wAAD vs P0 [95% CI] | Fighter-sqn-equiv. | CRaR10 |
|---|---|---|---|---|---|
| normal | P0 Reactive | 65.9% | 0 | 0 | 62.4% |
| normal | P1 Prediction-only | 62.9% | **−675** [−757, −593] | −0.10 | 59.9% |
| normal | P2 Predict+Spares+Schedule | 68.2% | +408 [298, 517] | +0.06 | 64.9% |
| normal | P2 + smart routing | 70.0% | +949 [704, 1,194] | +0.14 | 66.4% |
| normal | P2 + rogue quarantine | 67.6% | +274 [179, 369] | +0.04 | 64.6% |
| normal | P2 + MRV portfolio | 67.5% | +289 [185, 393] | +0.04 | 64.6% |
| normal | **P3 NIRANTAR** | **70.1%** | **+968 [757, 1,180]** | **+0.15** | **66.5%** |
| supply shock | P0 Reactive | 62.0% | 0 | 0 | 58.3% |
| supply shock | P1 Prediction-only | 59.5% | **−565** [−662, −468] | −0.09 | 56.4% |
| supply shock | P2 Predict+Spares+Schedule | 64.3% | +394 [290, 498] | +0.06 | 60.2% |
| supply shock | P2 + smart routing | 70.6% | +2,039 [1,827, 2,250] | +0.31 | 67.7% |
| supply shock | P2 + rogue quarantine | 63.6% | +232 [140, 324] | +0.04 | 59.3% |
| supply shock | P2 + MRV portfolio | 63.9% | +334 [250, 418] | +0.05 | 59.1% |
| supply shock | **P3 NIRANTAR** | **70.5%** | **+1,996 [1,797, 2,196]** | **+0.30** | **66.9%** |

The 5-year history ends with Russian supply in the *stressed* regime and 33 aircraft waiting for parts; forecasts start from that real state (see §4), which is why every curve in the console climbs out of a dip in the first month.

### 3.2 What the experiment says (honestly)

1. **Prediction alone makes things worse.** P1 loses 565–675 weighted aircraft-days. Alert-driven swaps pull serviceable-but-aged parts off aircraft, consume shelf spares and load repair agencies. This reproduces the central claim of Doc 1 §3.2 mechanistically: aircraft wait more than they break.
2. **The gains come from the repair network and logistics.** P2's logistics features turn prediction from harmful to useful (+394 to +408).
3. **NIRANTAR roughly doubles to quintuples P2's gain.** +968 in normal operations and **+1,996 under a supply shock (≈0.30 fighter-squadron-equivalents a year for a 70-aircraft force)**. Tail-risk availability (CRaR10) under shock is 66.9% vs 58.3% for the status quo.
4. **One lever does most of the work:** capacity- and quality-aware routing, built on SUSHRUTA's repair-quality estimates plus queue awareness, which avoids routing into sanction-stretched shipping lanes and overloaded depots.
5. **Rogue quarantine and the analytic spares portfolio add little on their own in year one** (+232 to +334). Deep-stripping rogues takes units out of circulation longer, with the payoff arriving later (needs a multi-year horizon), and the analytic portfolio screen is no better than "buy what was consumed". Both are Milestone 2 items.
6. **Single-spare MRVs are honest about uncertainty.** Several one-unit purchases have 95% intervals that include zero; the console labels them "Uncertain, needs more evidence" and the recorded decision is *defer*. A Russian-sourced unit that cannot arrive within 12 months while supply is stressed is shown as "No effect within horizon".
7. **Cost of delay:** the top-ranked spare loses ~1.2 weighted aircraft-days of value for every day its order waits.

### 3.3 Recovering hidden truth from records alone

| Quantity | Truth | Estimate [90% CI] |
|---|---|---|
| q, MSME-P (poor repairer) | 0.60 | 0.52 [0.41, 0.63] |
| q, BRD-1 | 0.25 | 0.31 [0.22, 0.41] |
| q, HAL-K | 0.15 | 0.12 [0.07, 0.21] |
| q, OEM-RU | 0.05 | 0.14 [0.07, 0.26] (slightly high) |
| Salinity effect on drivetrain life | 0.45× | relative 0.62× [0.56, 0.68] (truth relative ≈ 0.59×) |
| Dust effect on ECS turbine life | 0.55× | relative 0.71× [0.65, 0.77] (truth relative ≈ 0.74×) |
| Rogue serials (3% planted at 4× hazard) | 31 units | 16 flagged, **14 true (precision 0.88)**, recall 0.44 |
| Planted environment-mode effects (4) | — | 1 confirmed signal, **0 false signals**; 3/4 surfaced as candidates |
| Injected record defects (4 types) | — | **100% caught**; clean history: 0 false issues |
| Ledger tampering | — | every edit detected (entry + tree head) |

*Relative* environment multipliers compare one environment with the family's average across its environments, which is what records can identify.

---

## 4. Engineering decisions worth knowing

- **Common random numbers keyed by slot.** Failure draws are keyed by (tail, position, n-th installation), so two runs that fit different serials into a slot still share its random stream. This cut MRV noise about 3× versus serial-keyed draws.
- **Supply regimes stretch shipping, not service.** Sanctions and payment friction lengthen transit/customs/payment time; agency capacity is unchanged. An earlier version that stretched service time produced unbounded queues and an unrealistic, decaying baseline.
- **Agency capacity sized to ~72% utilisation** under status-quo routing, so the baseline is stationary and P3's routing gains are not artefacts of a saturated agency.
- **Gamma frailty in Tier C.** Without it, rogue units biased agency q upward. With it, estimates move towards truth.
- **Exposure-normalised signals.** Composition-only disproportionality produced "mirror" false alarms. Requiring a rate-ratio excess removed them.
- **Analytic gradients.** The Tier C posterior gradient is checked against finite differences in the test suite.
- **Forecasts continue the supply regime history ended in.** An earlier version restarted every forecast in the "normal" regime, which made recovery from the end-of-history dip look faster than it should.
- **Signed entries are immutable.** The ledger stores its own deep copy of each payload, so code that later edits the dict it logged cannot silently change a signed entry (a test caught exactly this).
- **Strict JSON.** Reports replace NaN/inf with null so browsers can parse them.

---

## 5. Limitations (Milestone 1)

- Synthetic world only; real effect sizes must come from shadow-mode pilots on sanitised service data.
- One supply-shock scenario; no war-surge (RANNITI), AKSHAYA life tracking, Tier A sensor models, SAARTHI or UI yet.
- Portfolio optimisation uses an analytic screen; it should be replaced by simulation-in-the-loop selection.
- Policies use plug-in estimates (no parameter uncertainty propagated into decisions).
- Rogue recall is modest (0.44) with 5 years of data; precision is the priority (no false accusations).

---

## 6. Next milestones

| Milestone | Content |
|---|---|
| **M2: Decisions** | Simulation-in-the-loop portfolio (OCBA), multi-year rogue evaluation, parameter-uncertainty-aware policies, ensemble data assimilation and forecast verification (CRPS/PIT), stress-test library, RANNITI surge mode |
| **M3: Sensors** | DHANVANTARI Tier A on NASA N-CMAPSS (engines) and DSTG HUMS2023 (gearbox) with conformal intervals; plug-in interface for external models (e.g. an engine health index) |
| **M4: People** | Console done early (see §2.1). Remaining: Base Huddle and BRD Queue role views, SAARTHI offline Hindi/English voice capture |
| **M5: Integration** | e-MMS/IMMOLS-shaped connectors, ontology, entity resolution, FAA SDRS real-data validation of SUSHRUTA/DRISHTI, security hardening (KAVACH) |
