# NIRANTAR

**National Intelligent Readiness & Airworthiness Network for Total Asset Reliability**
*(निरंतर: "continuous, uninterrupted")*

A sovereign decision platform for military aircraft predictive maintenance and fleet availability, being developed as a real system for the problem the Ministry of Defence posed as **SIH26249: "Air Power – Predictive Maintenance & Fleet Availability"** (MoD / DSSC).

## Research documents

| # | Document | What it covers |
|---|---|---|
| 1 | [Problem Statement Deep Dive](docs/01_PROBLEM_STATEMENT_DEEP_DIVE.md) | The problem in depth: availability maths, squadron gap, fleet-by-fleet CAG evidence, root causes, data landscape, why it is still unsolved, stakeholders, requirements, KPIs |
| 2 | [Existing Solutions Landscape](docs/02_EXISTING_SOLUTIONS_LANDSCAPE.md) | Everything others have built: USAF PANDA/CBM+, F-35 ALIS/ODIN, US Navy NSS-A, EXPRESS, RBS/METRIC, LCOM, UK/France/Israel, Indian initiatives, commercial platforms, academic research, open datasets, GitHub/OSS, every public SIH26249 team repo, standards, capability matrix, white space |
| 3 | [NIRANTAR Proposed Solution](docs/03_NIRANTAR_PROPOSED_SOLUTION.md) | The proposed solution: readiness-as-a-currency (Marginal Readiness Value), Sustainment Digital Twin with Readiness-at-Risk, Truth & Trust stack, 14 modules, maths, governance (ETAI), security, synthetic-data strategy (BHARAT-FLEET), hackathon MVP, validation plan, roadmap, ROI, pitch and Q&A |
| 4 | [Milestone 1: Engine Core](docs/04_MILESTONE_1_ENGINE.md) | What is built so far, how to run it, results on synthetic data, honest findings and limitations |
| 5 | [Milestone 2: SAARTHI snag entry](docs/05_MILESTONE_2_SAARTHI.md) | Speak or type a snag in Hindi, Hinglish or English; schema-constrained extraction, checks against the records, signed entries; accuracy and limits |
| 6 | [Milestone 3: Decision desk](docs/06_MILESTONE_3_DECISION_DESK.md) | Today's fleet board, a priced plan (cannibalisation, transfer, expedite, purchase), approvals by the right authority signed into the ledger, fresh-future check |
| 7 | [Milestone 4: Operations clock](docs/07_MILESTONE_4_OPERATIONS_CLOCK.md) | Run the station day by day: approved actions applied and signed, a shadow fleet on identical events measures what the decisions bought |
| 8 | [Milestone 5: Crisis mode](docs/08_MILESTONE_5_CRISIS_MODE.md) | Declare a supplier disruption on any day; both fleets feel it, the desk re-plans (re-routing to Indian depots, expediting), the clock measures the result |
| 9 | [7-minute demo script](docs/09_DEMO_SCRIPT.md) | A stakeholder briefing storyline as a presenter script; built into the console as **Guided demo** with live numbers and one-click steps |
| 10 | [Data foundation: planning from records](docs/10_DATA_FOUNDATION.md) | Import e-MMS/IMMOLS-style records with checks and quarantine; estimate the world, today's fleet state and the supply regime from records alone; run the console on them; back-test plans from records against the hidden truth |
| 11 | [Validation on real public data, and refitting](docs/11_REAL_DATA_VALIDATION.md) | DHANVANTARI on real field records (fans, 52k hard drives, engine valve seats, braking-grid batches) scored out of sample; per-part wear-out shape added; `refit` back-tests, chooses, flags drift and signs a model card |
| 12 | [Production deployment](docs/12_PRODUCTION_DEPLOYMENT.md) | Sign-in and server-enforced roles, each person's own signing key, HTTPS, storage safe for several writers, signed and verified backups, and installation without internet from a signed bundle |
| 13 | [SAARTHI field readiness](docs/13_SAARTHI_FIELD.md) | Real logbook English (6,169 entries, held-out evaluation and adjudication), the illustrated parts catalogue as vocabulary with part-number links, NATO-alphabet tail numbers, speech recognised on the node, and the field-trial protocol |
| 14 | [Scale](docs/14_SCALE.md) | Synthetic fleets up to 1,692 aircraft, 6 types, 24 bases and 107,000 units; actions priced on the bases they affect (exact), cached random draws, pruned refinement; the full record-to-plan path timed at each size |

## Development

```bash
python -m pip install -e ".[dev]"  # numpy, scipy, pandas, cryptography, pytest
python -m pytest -q                # 140 tests (1 needs a speech model)
python -m nirantar demo --quick    # ~15 s end-to-end run
python -m nirantar demo            # full run -> experiments/results/milestone1_report.md
python -m nirantar serve           # web console -> http://127.0.0.1:8050
python -m nirantar plan            # prepare today's decision-desk plan
python -m nirantar saarthi-eval    # SAARTHI extractor benchmark
python -m nirantar export-synthetic --out data/exports/bharat-fleet   # records in e-MMS/IMMOLS shape
python -m nirantar import data/exports/bharat-fleet --db data/nirantar.db
python -m nirantar serve --db data/nirantar.db   # console plans from the records
python -m nirantar records-backtest  # plan from records, score in the hidden truth
python -m nirantar refit --db data/nirantar.db   # refit, back-tested on the last year, signed model card
python -m nirantar validate-public   # DHANVANTARI on real public reliability data
python -m nirantar users add NAME --roles "CEngO"   # accounts for secure mode (docs/12)
python -m nirantar serve --auth experiments/results/users.db --cert C --key K --host 0.0.0.0
python -m nirantar backup --db data/nirantar.db --users experiments/results/users.db
python -m nirantar bundle --out dist/offline   # offline install bundle (docs/12)
python -m nirantar selftest          # acceptance check on a fresh node
python -m nirantar logbook-eval      # SAARTHI on 6,169 real maintenance logbook entries
python -m nirantar serve --asr-model en=MODEL_FOLDER   # voice snags recognised on the node (docs/13)
python -m nirantar asr-trial FOLDER --asr-model en=MODEL_FOLDER   # word error rate on field recordings
python -m nirantar scale-bench --size XL   # records-to-plan timings on a 1,692-aircraft fleet (docs/14)
```

On Windows machines where an Application Control policy blocks `pip.exe` or `pytest.exe`, use the `python -m ...` forms above; they run through `python.exe`.

| Package | Module (Doc 3) | Role |
|---|---|---|
| `nirantar/bharat_fleet` | BHARAT-FLEET | Synthetic world with hidden ground truth |
| `nirantar/sanjaya` | SANJAYA | Sustainment digital twin, ensembles, Readiness-at-Risk, operations clock |
| `nirantar/dhanvantari` | DHANVANTARI | Tier C reliability (hierarchical Weibull + Kijima + frailty) |
| `nirantar/sushruta` | SUSHRUTA | Agency repair quality, rogue serials |
| `nirantar/drishti` | DRISHTI | Airworthiness pharmacovigilance signals |
| `nirantar/satya` | SATYA | Data-quality invariants, Evidence Grades |
| `nirantar/chitragupta` | CHITRAGUPTA | Signed Merkle evidence ledger |
| `nirantar/chanakya` | CHANAKYA | Marginal Readiness Value, Cost-of-Delay, portfolios, decision desk |
| `nirantar/vishwakarma` | VISHWAKARMA | Readiness-weighted indigenisation ranking |
| `nirantar/saarthi` | SAARTHI | Voice/text snag entry: Hindi, Hinglish, English to a checked, signed record |
| `nirantar/setu` | SETU | Record store, mapped and checked import of e-MMS/IMMOLS-style exports, estimation of the world and fleet state from records, back-test against the truth |
| `nirantar/pariksha` | PARIKSHA | Validation on real public field data (vendored with sources) |
| `nirantar/rakshak` | RAKSHAK | Accounts, roles, sessions, personal signing keys, TLS certificates |
| `nirantar/ui` | Console | Offline web console with a guided 7-minute demo: readiness room, live what-if, decision desk, SAARTHI snag entry, opportunities, agencies, signals, indigenisation, ledger |

All data in this repository is synthetic. No number is an IAF result.
