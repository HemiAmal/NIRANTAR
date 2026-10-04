# NIRANTAR — Milestone 1: The Engine Core

> **Status:** built, tested (45 tests passing), and run end-to-end on synthetic data.
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
pip install -e ".[dev]"        # numpy, scipy, pandas, cryptography, pytest
python -m pytest -q            # 45 tests, ~10 s
python -m nirantar demo --quick   # ~15 s, fewer seeds
python -m nirantar demo           # full run, ~60 s -> experiments/results/
```

---

## 3. Results (full run: 5-year history, 365-day horizon, 20 paired seeds per arm)

### 3.1 Four-policy experiment

Policies (Doc 3 §13.2): **P0** reactive status quo · **P1** prediction-only (swap high-risk parts at inspection) · **P2** prediction + spares + scheduling (P1 + lateral transfers, need-based return, AOG priority) · **P3 NIRANTAR** (P2 + capacity/quality-aware routing + rogue quarantine + CHANAKYA portfolio). All arms get the same ₹6 crore spares budget: P0–P2 spend it the status-quo way (by last year's consumption), P3 spends it by CHANAKYA. Ablation rows add one NIRANTAR component at a time to P2.

Δ wAAD = change in role-weighted aircraft-available-days vs P0 on identical random streams (95% CI). CRaR10 = mean availability in the worst 10% of futures.

| Scenario | Policy | Availability | Δ wAAD vs P0 [95% CI] | Fighter-sqn-equiv. | CRaR10 |
|---|---|---|---|---|---|
| normal | P0 Reactive | 69.4% | 0 | 0 | 66.6% |
| normal | P1 Prediction-only | 65.7% | **−867** [−957, −778] | −0.13 | 62.8% |
| normal | P2 Predict+Spares+Schedule | 71.4% | +311 [230, 393] | +0.05 | 67.7% |
| normal | P2 + smart routing | 71.1% | +345 [109, 580] | +0.05 | 67.9% |
| normal | P2 + rogue quarantine | 70.9% | +194 [103, 285] | +0.03 | 67.5% |
| normal | P2 + MRV portfolio | 70.9% | +251 [138, 364] | +0.04 | 68.3% |
| normal | **P3 NIRANTAR** | 70.7% | +280 [79, 482] | +0.04 | 67.9% |
| supply shock | P0 Reactive | 64.8% | 0 | 0 | 61.2% |
| supply shock | P1 Prediction-only | 61.7% | **−700** [−770, −630] | −0.11 | 58.6% |
| supply shock | P2 Predict+Spares+Schedule | 67.1% | +410 [301, 519] | +0.06 | 62.7% |
| supply shock | P2 + smart routing | 70.8% | +1,458 [1,229, 1,687] | +0.22 | 68.0% |
| supply shock | P2 + rogue quarantine | 66.8% | +335 [233, 436] | +0.05 | 62.4% |
| supply shock | P2 + MRV portfolio | 67.7% | +605 [486, 723] | +0.09 | 63.1% |
| supply shock | **P3 NIRANTAR** | **70.9%** | **+1,462 [1,252, 1,671]** | **+0.22** | **67.0%** |

### 3.2 What the experiment says (honestly)

1. **Prediction alone makes things worse.** P1 loses ~700–870 weighted aircraft-days. Alert-driven swaps pull serviceable-but-aged parts off aircraft, consume shelf spares and load repair agencies. This is the central claim of Doc 1 §3.2 (aircraft wait more than they break), now reproduced mechanistically.
2. **The gains come from logistics and the repair network.** P2's logistics features (transfers, need-based return, AOG priority) turn prediction from harmful to useful.
3. **NIRANTAR's value concentrates in stress.** Under a Russian-supply disruption, P3 recovers **+1,462 weighted aircraft-days (≈0.22 fighter-squadron-equivalents a year for a 70-aircraft force)** and holds tail-risk availability (CRaR10) at 67% vs 61% for the status quo. In normal conditions P3 is statistically tied with P2. Its job is resilience: Readiness-at-Risk is where it pays.
4. **Most of the stress gain comes from one lever:** capacity- and quality-aware routing (SUSHRUTA's q estimates + queue awareness), which avoids routing into shipping lanes stretched by sanctions.
5. **Rogue quarantine costs readiness in year one.** Deep-stripping rogue units takes them out of the pipeline longer; the reliability payoff arrives later. It needs a multi-year horizon to evaluate fairly (Milestone 2).
6. **The analytic portfolio is not yet a big win.** CHANAKYA's analytic screen beats the status-quo "buy what was consumed" rule under shock (+605 vs +410) but not in normal times, and adds little once smart routing is on. Simulation-in-the-loop optimisation (OCBA ranking-and-selection) is the Milestone 2 fix.
7. **Single-spare MRVs are honest but wide.** The CIs on one-unit purchases often include zero even with 16 paired seeds, and the evidence gating correctly marks them *defer*. Portfolio-level decisions are much better determined than single-unit ones.

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
| **M4: People** | Readiness Room / Base Huddle / BRD Queue web consoles; SAARTHI offline Hindi/English voice capture |
| **M5: Integration** | e-MMS/IMMOLS-shaped connectors, ontology, entity resolution, FAA SDRS real-data validation of SUSHRUTA/DRISHTI, security hardening (KAVACH) |
