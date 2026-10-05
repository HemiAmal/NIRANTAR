# NIRANTAR

**National Intelligent Readiness & Airworthiness Network for Total Asset Reliability**
*(निरंतर: "continuous, uninterrupted")*

A proposed sovereign decision platform for military aircraft predictive maintenance and fleet availability. It addresses Smart India Hackathon 2026 problem statement **SIH26249: "Air Power – Predictive Maintenance & Fleet Availability"** (Ministry of Defence / DSSC).

## Research documents

| # | Document | What it covers |
|---|---|---|
| 1 | [Problem Statement Deep Dive](docs/01_PROBLEM_STATEMENT_DEEP_DIVE.md) | The problem in depth: availability maths, squadron gap, fleet-by-fleet CAG evidence, root causes, data landscape, why it is still unsolved, stakeholders, requirements, KPIs |
| 2 | [Existing Solutions Landscape](docs/02_EXISTING_SOLUTIONS_LANDSCAPE.md) | Everything others have built: USAF PANDA/CBM+, F-35 ALIS/ODIN, US Navy NSS-A, EXPRESS, RBS/METRIC, LCOM, UK/France/Israel, Indian initiatives, commercial platforms, academic research, open datasets, GitHub/OSS, every public SIH26249 team repo, standards, capability matrix, white space |
| 3 | [NIRANTAR Proposed Solution](docs/03_NIRANTAR_PROPOSED_SOLUTION.md) | The proposed solution: readiness-as-a-currency (Marginal Readiness Value), Sustainment Digital Twin with Readiness-at-Risk, Truth & Trust stack, 14 modules, maths, governance (ETAI), security, synthetic-data strategy (BHARAT-FLEET), hackathon MVP, validation plan, roadmap, ROI, pitch and Q&A |
| 4 | [Milestone 1: Engine Core](docs/04_MILESTONE_1_ENGINE.md) | What is built so far, how to run it, results on synthetic data, honest findings and limitations |

## Development (Milestone 1: engine core)

```bash
pip install -e ".[dev]"            # numpy, scipy, pandas, cryptography, pytest
python -m pytest -q                # 52 tests
python -m nirantar demo --quick    # ~15 s end-to-end run
python -m nirantar demo            # full run -> experiments/results/milestone1_report.md
python -m nirantar serve           # web console -> http://127.0.0.1:8050
```

| Package | Module (Doc 3) | Role |
|---|---|---|
| `nirantar/bharat_fleet` | BHARAT-FLEET | Synthetic world with hidden ground truth |
| `nirantar/sanjaya` | SANJAYA | Sustainment digital twin, ensembles, Readiness-at-Risk |
| `nirantar/dhanvantari` | DHANVANTARI | Tier C reliability (hierarchical Weibull + Kijima + frailty) |
| `nirantar/sushruta` | SUSHRUTA | Agency repair quality, rogue serials |
| `nirantar/drishti` | DRISHTI | Airworthiness pharmacovigilance signals |
| `nirantar/satya` | SATYA | Data-quality invariants, Evidence Grades |
| `nirantar/chitragupta` | CHITRAGUPTA | Signed Merkle evidence ledger |
| `nirantar/chanakya` | CHANAKYA | Marginal Readiness Value, Cost-of-Delay, portfolios |
| `nirantar/vishwakarma` | VISHWAKARMA | Readiness-weighted indigenisation ranking |
| `nirantar/ui` | Console | Offline web console: readiness room, live what-if, opportunities, agencies, signals, indigenisation, ledger |

All data in this repository is synthetic. No number is an IAF result.
