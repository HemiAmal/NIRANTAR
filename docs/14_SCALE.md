# Scale: from one station to an air force's fleet

> **Status:** built and tested. NIRANTAR was run end to end on synthetic fleets of up to about 1,700 aircraft: six aircraft types, 24 bases, 180 part numbers and 107,000 installed units. The planner, the twin and the record path were made fast enough for that size on a 4-core machine, without changing any result.
>
> Synthetic data (BHARAT-FLEET, scaled). Timings are from a 4-core cloud container.

```bash
python -m nirantar scale-bench --size XL      # -> experiments/results/scale_bench_XL.json
```

---

## 1. The fleets

| Size | Aircraft | Types | Bases | Part numbers | Installed units | Records over 5 years (installations) |
|---|---|---|---|---|---|---|
| S (default) | 70 | 2 | 4 | 16 | 1,050 | 3,600 |
| M | 288 | 3 | 6 | 60 | 13,600 | 39,600 |
| L | 846 | 6 | 12 | 150 | 44,600 | 139,300 |
| XL | 1,692 | 6 | 24 | 180 | 107,000 | 327,200 |

The scaled worlds (`bharat_fleet/scale.py`) generate part catalogues by system family, with origins and approved repair agencies. Depot capacity grows with repair demand at the default world's utilisation. The default 70-aircraft world, and every result published from it, is unchanged.

---

## 2. What was slow, and what changed

**Planning was the bottleneck.** Today's plan prices every candidate action (cannibalisation, transfer, expedite, priority, purchase, re-routing) on 24 paired simulated futures. Candidates grow with the number of grounded aircraft (1,022 at size L), and each future simulated the whole fleet. At size M a plan took 744 s; at L or XL it would have taken hours.

**1. Price each action where it can have an effect.**
- Aircraft types share no part numbers.
- Under today's procedures, a repaired unit returns to the base that sent it and bases do not lend to each other.
- So a cannibalisation, expedite, priority or purchase at one base is priced on a twin of **that base's aircraft of that type**; a transfer on its two bases; a re-routing on the type's whole fleet.
- Each aircraft keeps its identity in the full fleet, so it draws exactly the same failures and turnarounds as in a whole-fleet simulation.
- Checked: base and type views reproduce the whole-fleet simulation **exactly** (identical availability and waiting-days for every base, in every future).
- They stop being exact only when a repair depot's capacity binds across bases. The chosen plan is therefore always verified once on the whole fleet.
- Under policies that lend between bases or ship to the neediest base, the planner prices on whole aircraft types instead.

**2. Reuse random draws.**
- Every candidate is compared on the same futures, so the same random draws recur thousands of times.
- The first draw of each keyed generator is cached. It is the identical value, so results stay bit-for-bit the same.

**3. Do not refine what cannot be chosen.**
- After screening on 8 futures, only actions within 5 of the best for some grounded aircraft are refined on all 24.
- At M this cost 1.2% of plan value (+444 vs +449 aircraft-days, inside the ±44 uncertainty) for half the time.
- It applies only to fleets of 150 aircraft or more.

**4. Remove whole-fleet work from small runs, and quadratic loops from the record path.**
- Views carry only their own units' repair history.
- Each unit's frailty array is built once per world.
- Rebuilding today's state from records had two loops that scanned the whole fleet for every unit; they are now lookups.
- The checked import validates canonical timestamps without `strptime` and inserts rows in batches.

| Plan, 90 days, 24 futures | Before | After | Same plan? |
|---|---|---|---|
| M (288 aircraft) | 744 s | 144 s | 30 of 32 actions; value −1.2% (pruning) |
| L (846 aircraft) | 982 s (type views only) | **322 s** | identical: 60 actions, +612 [536, 687] |
| XL (1,692 aircraft) | (hours) | **1,479 s (25 min)** | verified on the whole fleet |

The test suite, which runs many simulations, went from 176 s to 101 s.

---

## 3. End to end at XL

1,692 aircraft, 24 bases, 180 part numbers, 106,962 installed units; 4 cores. From `experiments/results/scale_bench_XL.json`.

| Stage | What it does | Time |
|---|---|---|
| World | Build the fleet, parts, depots and suppliers | 0.5 s |
| History | Simulate 5 years of operation (the stand-in for real records) | 54 s |
| Frames | Turn installations into reliability data with prior-repair history | 2 s |
| Reliability fit | Fit every part number's failure model (Tier C) | 19 s |
| Export | Write the records as e-MMS/IMMOLS-shaped files | 14 s |
| Checked import | Validate, quarantine and store 327,183 installations, 231,768 repairs and snags, 222,772 receipts | **25 s** (was 124 s) |
| Estimate | Rebuild the world, today's fleet state and the supply regime from records alone | **64 s** (was 253 s) |
| Plan | Price 2,854 candidate actions, refine 1,634, choose and verify on the whole fleet | **1,479 s** |
| Ledger | Append 20,000 signed entries / verify the chain | 6 s / 2 s |

- **The plan:** 92 actions worth **+1,349 aircraft-days [1,229, 1,468]** of availability over 90 days, verified on the whole fleet.
- **Records to plan** takes about 27 minutes, nearly all of it pricing. A daily plan prepared overnight or at shift change fits easily.
- **Peak memory** is 2.8 GB.
- The estimate flagged the same 1,356 rogue units before and after the speed-ups. Each speed-up was checked against the old code on the L store: identical state, prior-repair columns and imported rows.

---

## 4. Limits

- **One machine.** Pricing parallelises across processes (4 here). A 32-core server would cut the plan time about 8×; distributing it across machines is not built.
- **Exactness of views** holds while repair depots are not saturated across bases; the whole-fleet verification of the chosen plan shows any interaction.
- **Pruning** trades about 1% of plan value for half the time; it can be switched off (`prune=False`).
- **SQLite** holds XL's records (about 330,000 installations over 5 years) comfortably. A multi-station deployment sharing one store would move to PostgreSQL (docs/12).
