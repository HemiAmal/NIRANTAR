# Validation on real public data, and refitting (PARIKSHA)

> **Status:** built and tested (113 tests passing in the whole repository). DHANVANTARI, the reliability engine behind every forecast and plan, has been checked on four real public field datasets, each scored on records the fit did not see. The checks changed the model: part numbers can now have their own wear-out shape. A `refit` command re-estimates the model as records arrive, chooses between variants on the last year of records, flags drift, and signs a model card into the ledger.
>
> These are real records, but **not aircraft-fleet records of any air force**. No public dataset joins aircraft installations, repairs and supply the way e-MMS and IMMOLS do. Each dataset tests one assumption NIRANTAR depends on. Sources and licences: `nirantar/pariksha/datasets/SOURCES.md`.

```bash
python -m nirantar validate-public              # -> experiments/results/public_validation.json (about 20 s)
python -m nirantar refit --db data/nirantar.db  # back-test, choose, register, sign
```

---

## 1. The datasets and what each one tests

| Dataset | Records | The question for NIRANTAR |
|---|---|---|
| Diesel-generator fans (Nelson) | 70 fans, 12 failures, hours | Does the fit estimate what it claims? (against an independent fit) |
| Hard drives (Backblaze, via `frailtySurv`) | 52,422 drives, 85 models, 2,885 failures | With many part numbers, most of them sparse, does sharing strength across a family predict failures of held-out units better than fitting each part number alone, or all together? |
| Diesel-engine valve seats (Nelson & Doganaksoy) | 41 engines, 48 replacements over 2 years | Does a unit's own record (the frailty behind rogue-unit detection) improve the forecast of its future failures? Is repair modelled sensibly? |
| Locomotive braking grids (Doganaksoy & Nelson) | 83 grids from 2 manufacturing batches, 50 replacements | Can a worse batch, lot or repair source be told apart, and does the engine admit when it cannot? |

Each dataset is loaded as the same installation spells that come out of the SETU record store (`pariksha/public.py`). The mapping:

| Dataset | Part number | Family | Environment | Unit |
|---|---|---|---|---|
| Drives | drive model | maker | temperature band | the drive |
| Valve seats | valve seat | — | — | the engine; the engine shop is a repair agency whose repair effectiveness q is estimated |
| Braking grids | one per batch | braking grid | — | the locomotive |

The fits use the same code and priors as for fleet records. Nothing was tuned to these data.

---

## 2. Results

### 2.1 Fans: the fit agrees with an independent maximum-likelihood fit

| Hours | 2,000 | 5,000 | 10,000 | 20,000 | 30,000 |
|---|---|---|---|---|---|
| P(failed), independent Weibull MLE (β 1.058, η 26,297 h) | 6.3% | 15.9% | 30.2% | 52.7% | 68.3% |
| P(failed), Tier C | 5.9% | 15.8% | 31.1% | 54.2% | 69.3% |

The largest difference is 1.5 points. Tier C's own parameters differ (β 1.15, η 22,611 h) because it also models unit-to-unit variation; the predicted failure probabilities, which are what planning uses, agree.

### 2.2 Hard drives: partial pooling wins where data is thin

Drives were split at random, half for fitting and half held out, three times. The score is the held-out log-likelihood: a failure counts at its time, a censored drive by its survival. A "sparse" model has 5 or fewer failures in the fitting half. Calibration is expected against observed failures per model, as Poisson deviance, using cumulative hazard, which stays unbiased under censoring.

| Method | Log-likelihood per 1,000 drives (all) | (sparse models) | Deviance by model (all) | (sparse) |
|---|---|---|---|---|
| One Weibull for all drives (complete pooling) | −569.7 | −435.7 | 2,210.8 | 146.4 |
| A Weibull per model, where it has ≥3 failures (no pooling) | −513.4 | −435.9 | 148.1 | 112.6 |
| Tier C, shape shared within a maker | −523.4 | −430.6 | 153.2 | 107.1 |
| **Tier C, each model its own shape (shrunk to its maker's)** | **−511.6** | −424.4 | **141.7** | 110.4 |

Higher log-likelihood is better; lower deviance is better.

With only 10% of the fitting half (about 2,600 drives), closer to the data a fleet has for a rare part:

| Method | Log-likelihood (all) | (sparse) | Deviance by model (all) | (sparse) |
|---|---|---|---|---|
| Complete pooling | −570.4 | −270.3 | 2,198.7 | 903.2 |
| No pooling | −522.7 | −252.8 | 467.4 | 385.4 |
| Tier C, shared shape | −529.8 | **−249.8** | **374.6** | **310.8** |
| Tier C, own shape | **−519.7** | −250.5 | 401.8 | 320.5 |

**What this showed, and what changed:**

- Treating all units of a type as one population (complete pooling) is badly calibrated: deviance about 15 times higher.
- Fitting each part number alone works only where it has enough failures. With 1 or 2 failures a per-model fit is degenerate, which is why that baseline needs a fallback at all. With little data it is the worst calibrated of the three.
- **The first finding against Tier C:** with plenty of data, separate fits beat Tier C overall. Drive models differ in how they wear out (shape), and Tier C shared one shape per maker. Tier C therefore now has an option for **each part number's own shape, shrunk towards its family's**. With it, Tier C is the best or close to the best on every score.
- Total expected failures are within ±4% of observed on the full data (e.g. 1,437 vs 1,412).

### 2.3 Valve seats: a unit's own record helps, modestly

There were three back-tests. At days 300, 400 and 500, the model was fitted on everything before the cut-off and predicted each engine's replacements until its last inspection.

| Prediction of each engine's future replacements | Poisson deviance (3 cut-offs) | Total predicted vs observed (day 300 / 400 / 500) |
|---|---|---|
| Tier C with the engine's own tendency (frailty posterior) | **131.6** | 31.4 / 20.5 / 9.9 vs **29 / 21 / 15** |
| Tier C, population only | 136.8 | 31.5 / 20.8 / 10.0 |
| Constant rate (no wear-out) | 142.3 | 20.2 / 14.8 / 8.1 |
| Each engine's own past rate | 1,036.5 | 19.2 / 13.8 / 7.5 |

**What this showed:**

- **Wear-out matters.** The fitted shape is β 1.2–1.4. A constant-rate forecast under-predicts at every cut-off, by 30% at day 300.
- **Repair is neither "as good as new" nor "as bad as old".** The engine shop's estimated repair effectiveness is q ≈ 0.45–0.47: a seat replacement removes about half of the engine's accumulated age. This is the Kijima model NIRANTAR uses for repair agencies, and it is stable across cut-offs.
- **A unit's own record helps:** deviance falls from 136.8 to 131.6. With 41 engines and 48 events the gain is small. Rogue-unit detection should therefore stay evidence-graded and conservative on small fleets, as it is.
- Using a unit's own rate alone is badly wrong for units with no past failures (it predicts zero).
- At day 500, all methods under-predict (15 observed vs about 10). Late replacements cluster in a few engines; a 2-year record cannot pin down the far tail.

### 2.4 Braking grids: says "not proven" when it is not

Batch 2 grids are estimated to last 0.71 times as long as batch 1 (90% interval 0.49–1.04), and were replaced at 3.2 vs 2.25 per 1,000 grid-days. The interval includes "no difference", so the evidence grade would not support a "bad batch" finding from 50 replacements. It would flag the batch for watching. This is the behaviour wanted for repair-source and lot comparisons (SUSHRUTA): the point estimate alone would have overstated it.

---

## 3. Refitting (`setu/refit.py`)

`python -m nirantar refit --db data/nirantar.db`:

1. **Back-test inside the store.**
   - Each candidate specification (shared or own shape per part number) is fitted on the records up to a year before the as-of date.
   - It is scored on what happened since: every unit in service after the cut-off contributes from its age then, using its own failure tendency from before.
   - Records are truncated as they stood at the cut-off: removals after it are still open, and hours at the cut-off are interpolated.
2. **Choose** the specification with the best held-out score and refit it on all records. The choice is evidence on each deployment's own records:
   - on the synthetic fleet, the shared shape wins narrowly (its parts share shapes within a family);
   - on the real drives, own shape wins.
3. **Drift.** Part numbers whose life, or agencies whose repair quality, moved by more than two combined standard errors since the previous version are listed for a reliability engineer.
4. **Model card.** The card holds the version, specification, data fingerprint (SHA-256 of the spells), held-out scores per part number, key parameters with standard errors, and drift flags. It is stored in the `models` table and signed into the ledger as `model_fit`. `estimate()` and the console use the registered specification.

On the synthetic 5-year store, the held-out year had 539 failures against 495 expected (−8%). The held-out score leaves out virtual age from earlier repairs (the same for both candidates), which under-counts repaired units' age.

---

## 4. Limits

- **None of this is military aircraft data.** The datasets test the statistical machinery (censoring, sparse part numbers, unit heterogeneity, imperfect repair, batch comparison) on real failures. The supply and repair-pipeline side (turnaround, regimes) has no public counterpart and is validated only on synthetic records (docs/10).
- **Drive temperature effects** are estimated, but temperature is confounded with model and rack location in this data, so no causal claim is made.
- **Real aviation maintenance text** (6,169 University of North Dakota logbook entries, via MaintNet and the AKGAM project) was found and is the basis of the SAARTHI field-readiness work (item 4). It has no dates or tail numbers, so it cannot test lifetimes.
