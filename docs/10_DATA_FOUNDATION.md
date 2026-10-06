# NIRANTAR data foundation: planning from records (SETU)

> **Status:** built and tested (104 tests passing in the whole repository). NIRANTAR can now run from maintenance and supply records alone: e-MMS-style installation, repair-order and defect files, plus IMMOLS-style stores receipts and stock. It imports and checks them, estimates the world and today's fleet state, and runs the Decision desk, Operations clock and SAARTHI on that estimate. A back-test plans from exported records and scores the plans in the hidden truth.
>
> All data is synthetic (BHARAT-FLEET exported in e-MMS/IMMOLS shape). No number here is an IAF result. The file layouts are representative, not the real systems' schemas; connecting a real export means writing its mapping file (§2).

Until this step every module read the simulator directly, including things no real system can see: each unit's true failure tendency, each agency's true repair quality, and the true supply regime. This step removes that dependency.

---

## 1. How to use it

```bash
python -m nirantar export-synthetic --out data/exports/bharat-fleet   # records in source-system shape
python -m nirantar import data/exports/bharat-fleet --db data/nirantar.db
python -m nirantar serve --db data/nirantar.db                         # console plans from the records
python -m nirantar plan --db data/nirantar.db                          # today's plan from the records
python -m nirantar records-backtest                                    # plan from records, score in the truth
```

With `--db`, the header banner reads *"Planning from records as of 2026-10-05 · synthetic export"*. Its tooltip lists the store and the documented gaps (§4). Records mode keeps its own operations clock and plans (`experiments/results/records/`), separate from the synthetic demo.

---

## 2. Import (SETU store)

| Piece | What it does |
|---|---|
| `setu/schema.py` | One SQLite file: masters (bases, fleets, aircraft, agencies, parts), events (installs, repair orders, defects, receipts, stock on hand), and ingest bookkeeping. Standard library only, so it suits an air-gapped node. The SQL is plain enough to move to PostgreSQL. |
| `setu/mappings/default.json` | Source file → table, source column → field, time format, code lists (removal reasons, work types, problem codes). **A new source is connected by writing a mapping file, not code** (tested with a renamed export). |
| `setu/ingest.py` | Row checks with quarantine and a reason: missing field, bad time, unknown part, part not fitted to that type, bad position, removal before installation, hours going backwards, repair dates out of order, duplicates. Then SATYA cross-record checks: a unit on two aircraft, overlapping installations. Each file is imported once (SHA-256), and each accepted batch is signed into the ledger as a `data_batch` entry. |
| `masters/supply_risk.json` | The supplier regime model (levels, delay multipliers, daily transitions). It is a planning assumption, kept as master data. |

Planted defects (2% of installation rows corrupted five ways) are all quarantined with the right reason, with no false rejections. A clean import fits the same reliability model as the simulator's own records.

---

## 3. Estimation (`setu/estimate.py`)

Everything the digital twin needs is estimated from the store:

| Quantity | Estimated from | How it compares to the hidden truth (day 1825) |
|---|---|---|
| Weibull shape per system, scale per part, environment effects, repair quality per agency | DHANVANTARI Tier C fit on installation spells | shape within 5% (median), scale within 17% |
| Each unit's failure tendency | Gamma-frailty posterior `(k + failures) / (k + expected)` | rogue units flagged with 88% precision (SUSHRUTA, same detector as the analysis) |
| Repair turnaround (median, spread) | Repair orders | within 6% at every agency |
| Shipping legs | Repair finished → received at base | exact (3, 3, 3, 12, 10 days) |
| Depot capacity | Peak concurrent repairs × 1.2 | a lower bound; it matters only when depots saturate |
| Failure-mode mix, signals, data quality | Defect reports (DRISHTI), SATYA checks | as in the analysis |
| **Today's supply regime** | Hidden-Markov forward filter (below) | a probability per regime |

**Fleet state at the as-of time:** what is fitted where, what is on the shelf, every unit in the repair pipeline with its expected remaining time, and how long each aircraft has waited for a part. On the synthetic history all of these match the truth exactly. Expected remaining repair time is unbiased across five histories (e.g. 38.1 vs 37.3 days). The error on any single unit is large (MAE 10 to 25 days), because the true completion time is a random draw no records can foresee.

**The supply-regime filter.** Shipping time is the agency's normal leg times the regime multiplier on the day a unit leaves. That gives three kinds of evidence:

- A completed return leg reveals the multiplier exactly.
- A repaired unit not yet received has been travelling at least that long, which is a lower bound.
- An outbound leg includes queueing, so it is an upper bound. A unit sent but not yet started is soft evidence of a long leg.

The regime model's transitions carry the belief forward to today. The result is honest uncertainty: when the latest evidence is a month old, "stressed" may be only 52% likely. Planning therefore **does not pick one regime**. Each simulated future starts from a regime drawn from the belief (`regime_probs` in the twin's start state), so plans are priced across the possibilities.

---

## 4. Known gaps (stated in the console)

1. **Inspections are not recorded yet.** Each aircraft's inspection timing is spread evenly over its interval.
2. **Purchase orders in flight are not recorded yet.** None are assumed.
3. **Work in progress on aircraft** (maintenance hands-on time) is not recorded, so it is assumed zero.

Each gap closes by adding its record type to the mapping and schema.

---

## 5. Back-test: plan from records, score in the truth

`python -m nirantar records-backtest` → `experiments/results/records_backtest.json`. There are five cases, each a different history or cut-off day. At each one:

1. The true fleet runs to the cut-off.
2. Its records are exported, imported and estimated.
3. Today's 90-day plan is built three ways:
   - **from records**, as a deployed NIRANTAR would;
   - by an **oracle** with the true state and world;
   - by an **oracle with records-level supply knowledge**: true state and world, but today's supply regime only as the records show it.
4. All three plans are scored in the true world on 32 futures none of the planners priced.

| Cut-off (history) | Supply regime true / estimated | Claimed | **Realised in truth** | Oracle | Oracle, supply as records | Regret from records (95% CI) |
|---|---|---|---|---|---|---|
| 1095 (99) | disrupted / stressed | +305 | **+306** | +342 | +327 | +21 [2, 41] |
| 1460 (99) | stressed 4 days / normal | +76 | **+81** | +184 | +73 | −8 [−17, 0] |
| 1825 (99) | stressed / stressed | +200 | **+164** | +167 | +162 | −2 [−21, 18] |
| 1500 (7) | normal / normal | +198 | **+183** | +151 | +151 | −32 [−46, −18] |
| 1825 (5) | stressed / stressed | +245 | **+227** | +180 | +177 | −50 [−66, −34] |

Values are weighted aircraft-available-days over 90 days against today's procedures.

**What this shows:**

- **Given the same supply knowledge, planning from records loses nothing measurable.** Mean regret is −14 aircraft-days; negative means the records plan did slightly better. Planning on 24 futures is noisy, so in any one case either planner can be the luckier.
- **The one large gap (day 1460) is information nobody had.** Russian supply turned stressed four days before the cut-off, before any shipment could show it. An oracle given the same supply knowledge does no better (+73).
- **The plan's claimed value is honest within about 12 aircraft-days on average.** It is slightly optimistic, which is expected because choosing the best-looking actions favours lucky estimates (the fresh-future check in docs/06 exists for this). The 90-day availability forecast from records is within −1.2 points of the truth on average (range −3.7 to +2.5).
- **What improved through the back-test:**
  - Shipping legs of units in transit now use the estimated regime.
  - The regime estimate became a calibrated filter instead of a median of recent legs.
  - Plans now integrate over the regime belief.

  Together these cut over-claiming from 34 to 12 aircraft-days and forecast bias from −2.0 to −1.2 points.

---

## 6. What this does not show

- The records are synthetic, so they follow the model's assumptions exactly (Weibull lives, Kijima repairs, lognormal turnaround). Real records will not. The next step is validation on real public reliability and maintenance data, refitting and back-testing on it.
- Data defects in the back-test are limited to what the importer quarantines. Subtle errors that pass the row checks (wrong but plausible hours, a mis-keyed serial) are not yet simulated.
