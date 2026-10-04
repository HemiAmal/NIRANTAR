# NIRANTAR — Document 2 of 3
# Existing Solutions Landscape: What Others Have Already Built

> **Purpose.** A complete catalogue of solutions to the military/aviation predictive-maintenance and fleet-availability problem: government and military programmes, commercial platforms, Indian initiatives, academic research, open datasets, open-source software and GitHub repositories, and **every publicly visible SIH 2026 team solution to the same problem statement (SIH26249)**.
>
> **Why this matters.** NIRANTAR must be *novel*. You can only claim novelty after mapping what already exists. This document is that map. Document 3 uses it to position NIRANTAR in the white space.
>
> **Note on content.** Each entry is a structured, detailed summary in our own words with a link to the original. We do not paste third-party text verbatim, both for copyright reasons and because summaries are easier to compare. Every substantive feature, number and claim we found is captured. Vendor performance numbers are *vendor claims* unless an independent source is cited.

---

## Table of Contents

1. [Taxonomy: the 12 layers of a solution](#1-taxonomy-the-12-layers-of-a-solution)
2. [Military and government programmes (worldwide)](#2-military-and-government-programmes-worldwide)
3. [Indian initiatives](#3-indian-initiatives)
4. [Commercial platforms and products](#4-commercial-platforms-and-products)
5. [Academic research streams](#5-academic-research-streams)
6. [Open datasets](#6-open-datasets)
7. [Open-source software and GitHub repositories](#7-open-source-software-and-github-repositories)
8. [SIH 2026 (PS SIH26249) team solutions on GitHub](#8-sih-2026-ps-sih26249-team-solutions-on-github)
9. [Standards, specifications and frameworks](#9-standards-specifications-and-frameworks)
10. [Comparative capability matrix](#10-comparative-capability-matrix)
11. [Lessons: what worked, what failed, and why](#11-lessons-what-worked-what-failed-and-why)
12. [Our initial draft ideas, re-checked against the landscape](#12-our-initial-draft-ideas-re-checked-against-the-landscape)
13. [White space: what nobody has built](#13-white-space-what-nobody-has-built)
14. [References](#14-references)

---

## 1. Taxonomy: the 12 layers of a solution

Each existing solution covers one or a few of these layers. Seeing them together explains why availability rarely improves when only one layer is bought.

| # | Layer | Question it answers | Typical tech |
|---|---|---|---|
| L1 | **Sensing / HUMS** | What is the aircraft experiencing? | Sensors, FDR, BITE, HUMS, vision cameras |
| L2 | **Records / MRO ERP** | What happened, what was done, what is in stock? | Maximo, AMOS, Maintenix, Ramco, e-MMS, IMMOLS |
| L3 | **Diagnostics & prognostics** | What is failing, and when will it fail? | Anomaly detection, RUL models, physics models |
| L4 | **Reliability engineering** | How long do parts last, and why do they fail? | Weibull/survival, RCM, MSG-3, rogue detection |
| L5 | **Spares optimisation** | How many of which spares, where? | METRIC/VARI-METRIC, RBS, OPUS10, ASM |
| L6 | **Repair prioritisation** | Which carcass to repair first? | EXPRESS-type daily optimisation |
| L7 | **Availability / sortie simulation** | What availability will we get under a given plan? | LCOM, SIMLOX, WITNESS, discrete-event simulation |
| L8 | **Structural / physical digital twin** | How much life has *this* airframe consumed? | ASIP IAT, AFRL ADT, FEM, crack growth |
| L9 | **Data platform / integration** | Is all the data in one place? | Skywise/Foundry, C3 AI platform, data lakes |
| L10 | **Process & governance** | Who decides, how fast, with what discipline? | NSS-A, Maintenance Operations Centers, PBL |
| L11 | **Human interface / copilots** | Can the maintainer use it? | Mobile apps, NLP, LLM/RAG copilots |
| L12 | **Contracting / accountability** | Who is paid for availability? | PBL, verticalised contracts (RAVEL) |

---

## 2. Military and government programmes (worldwide)

### 2.1 USAF PANDA: Predictive Analytics and Decision Assistant (Rapid Sustainment Office + C3 AI)

| Field | Detail |
|---|---|
| Owner | USAF Rapid Sustainment Office (RSO), AFLCMC |
| Vendor | C3 AI (enterprise AI platform) |
| Status | **Designated the USAF System of Record for CBM+ and predictive maintenance** (April 2023) |
| Scale | Deployed across **16 aircraft platform communities in all nine Major Commands**; routinely generates **>30,000 predictive-maintenance recommendations and sensor-based alerts** |
| Results | B-1: **complete elimination of unscheduled breaks** for targeted systems; **51% reduction in unscheduled maintenance man-hours** for those systems |
| Contract | Ceiling raised from $100M to **$450M** (2025), work through Oct 2029; covers B-1, C-5, KC-135, C-17, C-130J and more |
| How it works | Integrates logistics, maintenance and sensor data; AI/ML models produce alerts. **Three user roles:** *aircraft maintenance engineers* prioritise part replacements from alerts; *supply-chain analysts* ensure parts supply against AI forecasts; *maintainers* validate recommendations |
| Layers | L2→L3→L4→(L5 via supply analysts)→L9→L11 |
| Lessons | (1) Becoming a **system of record** turned a pilot into an institution. (2) **Human validation** is built in. (3) The **supply-analyst role** links prediction to provisioning, which is the key design move |
| Limits (public view) | Cloud-centric vendor platform; US-specific; per-platform models; little public evidence of explicit availability optimisation or geopolitical supply-risk modelling |
| Sources | [DefenseScoop 2023](https://defensescoop.com/2023/05/10/air-force-selects-ai-enabled-predictive-maintenance-program-as-system-of-record/), [AFLCMC](https://www.aflcmc.af.mil/NEWS/Article/3381920/rapid-sustainment-offices-condition-based-maintenance-plus-artificial-intellige/), [C3 AI](https://c3.ai/news/u-s-air-force-designates-c3-ai-predictive-maintenance-solution-as-system-of-record), [GovConWire 2025](https://www.govconwire.com/articles/air-force-awards-450m-contract-to-c3-ai-for-predictive-analytics), [Airforce Technology](https://www.airforce-technology.com/news/c3-ai-wins-450m-usaf-contract-mod-for-predictive-analytics-tech/) |

### 2.2 USAF CBM+ (Condition-Based Maintenance Plus): PAD and ERCM

| Field | Detail |
|---|---|
| Components | **PAD (Predictive Algorithm Development):** sensor and diagnostic data run through algorithms to estimate degradation. **ERCM (Enhanced Reliability-Centred Maintenance):** uses *decades of maintenance and supply data* to estimate how long each part will last and to forecast failures **up to two years ahead**, so maintenance can be arranged early |
| Early platforms | C-5M, KC-135R (10 bases), B-1 |
| Claimed impact | Potential **>$5.5B** savings fleet-wide; >550 maintenance units trained; ~5,000 hours of troubleshooting saved; ~250 sensor-based alerts that avoided in-flight failures |
| Significance for India | **ERCM is records-based reliability forecasting**, the same idea as "Weibull on e-MMS removal history". It is proven at scale. It is *not* novel by itself, but it is highly relevant for India's sensor-poor fleets |
| Sources | [Air Force Times](https://development.airforcetimes.com/?p=21195), [Air & Space Forces](https://www.airandspaceforces.com/amc-planning-large-expansion-of-predictive-maintenance-effort), [Dayton Aero](https://daytonaero.com/post/usaf-cbm-update-what-commercial-industry-oems-and-software-developers-need-to-know) |

### 2.3 F-35 ALIS → ODIN (Lockheed Martin / JPO)

| Field | Detail |
|---|---|
| What | **ALIS (Autonomic Logistics Information System):** the F-35's integrated logistics brain covering maintenance, supply, health, mission planning and training records. **ODIN (Operational Data Integrated Network):** its government-owned, cloud-enabled replacement |
| Cost | ALIS reported as a **$17B** system |
| Failure modes | DOT&E: "numerous workarounds, retains problems with data accuracy and integrity, and requires excessive time from support personnel". Records were "frequently incorrect, corrupt or missing", so ALIS **flagged airworthy jets for grounding**. One USAF unit estimated **>45,000 hours/year** of extra tasks and workarounds |
| ODIN status | Announced ~2020 for 2022; first fielding slipped to **2025**; Navy order for ODIN hardware ($47.6M) through Dec 2026 |
| GAO concerns | Unclear goals of the redesign; how much of ALIS carries over; DoD's **access to the data** needed for sustainment |
| Lessons | (1) **Data quality and maintainer trust decide success**, not model accuracy. (2) **Government data rights** are essential. (3) A monolithic, contractor-controlled, centralised system is fragile. (4) Workload added at the flight line kills adoption |
| Sources | [BloombergQuint](https://www.bloombergquint.com/business/f-35-s-17-billion-diagnostic-system-rife-with-flaws-gao-says), [Military.com](https://mst.military.com/daily-news/2020/03/20/watchdog-pentagon-needs-answer-questions-new-f-35-logistics-system.html), [TWZ](https://www.twz.com/31861/replacement-for-f-35s-troubled-alis-cloud-based-brain-rebranded-odin-and-is-still-years-away), [Defense Daily](https://defensedaily.com/start-of-f-35-odin-software-fielding-to-squadrons-delayed-until-2025/air-force), [GAO blog](https://gao.gov/blog/f-35-alis-looking-glass), [Military Aerospace](https://militaryaerospace.com/computers/article/55357534/lockheed-martin-lockheed-martin-to-handle-logistics-and-mission-planning-software-for-f-35-jet-fighter-bomber) |

### 2.4 US Navy NSS-A (Naval Sustainment System–Aviation) and the Maintenance Operations Center

| Field | Detail |
|---|---|
| Trigger | SecDef Mattis directive (Sep 2018): 80% mission-capable rate for F/A-18 E/F, EA-18G, F-35 and F-22 |
| Result | Navy hit **80% MC** for Super Hornets and Growlers by **Sep 2019**, up from ~50%, and reached the stretch goal of **341 "up" fighters** |
| How | Data-driven review of *people, parts and processes* using commercial best practice (with BCG). Reforms in O-level maintenance, Fleet Readiness Centers, engineering, supply, policy and safety. Created a **Maintenance Operations Center** that monitors daily aircraft status and **prioritises parts distribution, technical assistance and systemic fixes** |
| Lessons | **Governance plus daily data-driven prioritisation** gave the fastest readiness gains on record, *without* exotic AI. Sustaining the gains was harder |
| Sources | [USNI News](https://news.usni.org/2019/09/25/navy-surpasses-80-aircraft-readiness-goal-reaches-stretch-goal-of-341-up-fighters), [Navy.mil](https://www.navy.mil/Press-Office/Press-Releases/display-pressreleases/Article/2237257/naval-aviation-achieves-secdef-readiness-target-shifts-focus-to-readiness-susta/), [TWZ](https://www.twz.com/30006/navy-super-hornets-hit-big-80-percent-readiness-goal-but-sustaining-it-is-another-question.md) |

### 2.5 USAF EXPRESS (Execution and Prioritization of Repair Support System)

| Field | Detail |
|---|---|
| What | A daily optimisation tool that **prioritises depot repair of reparable spares** to maximise responsiveness to warfighter needs |
| How | Each day, for each reparable, at each Air Logistics Complex, EXPRESS compares the ideal plan to the actual state and recommends actions to re-synchronise, subject to carcass availability, repair capacity, budget and piece-parts |
| Governance | AFSC Instruction 23-103 (updated March 2026) |
| Research | Simulation studies of how EXPRESS run frequency affects MICAP (mission-impaired capability awaiting parts) hours |
| Lesson | **Readiness-driven repair prioritisation is an established concept** in the USAF. India's BRDs have no public equivalent |
| Sources | [AFSCI 23-103](https://static.e-publishing.af.mil/production/1/af_sustainment_ctr/publication/afsci23-103/afsci23-103.pdf), [DTIC study](https://apps.dtic.mil/sti/pdfs/ADA618371.pdf), [AFIT thesis](https://scholar.afit.edu/etd/1244) |

### 2.6 Readiness-Based Sparing (RBS): METRIC → VARI-METRIC → ASM → Navy RBS

| Model | Origin | What it does |
|---|---|---|
| **METRIC** (Multi-Echelon Technique for Recoverable Item Control) | Craig C. Sherbrooke, RAND/USAF, mid-1960s | Sets stock levels of expensive repairables across bases and a depot to **minimise expected backorders** (a proxy for aircraft down) for a budget. Basis of USAF reparable allocation for ~50 years |
| **MOD-METRIC / VARI-METRIC** | Muckstadt; Sherbrooke | Multi-indenture (LRU/SRU) and variance-corrected approximations |
| **Aircraft Sustainability Model (ASM)** | LMI for USAF (WSMIS/REALM) | Multi-echelon, multi-indenture model of **transient wartime demand**; links spares investment to **sortie-generation capability** during conflict |
| **Navy RBS** | NAVSUP WSS | Operations-research multi-echelon RBS for Navy readiness goals at minimum investment |
| **Lessons** | — | **Availability-driven spares optimisation is a 60-year-old proven science.** What it lacks: dynamic, condition-based demand inputs (it usually assumes stationary Poisson demand), geopolitical lead-time risk, and integration with repair-queue and scheduling decisions |
| Sources | [DTIC ADA207015](https://apps.dtic.mil/sti/pdfs/ADA207015.pdf), [DTIC ADA484288](https://apps.dtic.mil/sti/pdfs/ADA484288.pdf), [INFORMS/IDEAS](https://ideas.repec.org/a/inm/oropre/v34y1986i2p311-319.html), [Navy.mil RBS](https://www.navy.mil/Press-Office/News-Stories/display-news/Article/2856341/navsup-wss-using-operations-research-to-develop-multi-echelon-rbs-modeling/), [UMD review](https://drum.lib.umd.edu/handle/1903/2300) |

### 2.7 LCOM (Logistics Composite Model): USAF / RAND

| Field | Detail |
|---|---|
| What | Stochastic discrete-event simulation of a flying unit: flying, servicing, malfunctions, flight-line maintenance, back-shop repair, resources and shift policies |
| Use | Sets maintenance manpower levels to reach a target **sortie generation rate**; used by ACC, USAFE and AFMC |
| Origin | Late 1960s, RAND with Air Force Logistics Command |
| Lesson | **Sortie-generation simulation for maintenance planning is half a century old.** Modern versions need live data calibration and health-state inputs |
| Sources | [RAND RM5544](https://www.rand.org/pubs/research_memoranda/RM5544.html), [WSC 2007](https://www.informs-sim.org/wsc07papers/169.pdf), [DTIC LCOM workbook](https://apps.dtic.mil/sti/html/tr/ADA030753/index.html) |

### 2.8 AFRL Airframe Digital Twin (ADT) and ASIP Individual Aircraft Tracking

| Field | Detail |
|---|---|
| What | Probabilistic, prognostic **individual aircraft tracking (P2IAT)**: carries uncertainty in usage, geometry, materials and damage state through fatigue and crack-growth models for each tail. "SAFER-P2IAT" in ADT Spiral 1 |
| Basis | **ASIP (Aircraft Structural Integrity Program, MIL-STD-1530)**: durability and damage-tolerance life management |
| Update loop | Twin state updated from actual usage tracking, diagnostics and inspection/maintenance data |
| Lesson | **Per-tail structural lifing from usage** is mature in the USAF. For India it underpins evidence-based *life extension* and *retirement ordering*, a lever no SIH team uses |
| Sources | [DTIC AD1062259](https://apps.dtic.mil/sti/pdfs/AD1062259.pdf), [NATO STO AVT-369](https://www.sto.nato.int/publications/STO%20Meeting%20Proceedings/STO-MP-AVT-369/MP-AVT-369-10P.pdf), [ICAS 2024](https://www.icas.org/icas_archive/icas2024/data/papers/icas2024_0724_paper.pdf) |

### 2.9 US Army Aviation CBM+/HUMS and ground-vehicle AI pilots

| Field | Detail |
|---|---|
| Aviation | HUMS with **Digital Source Collectors** and condition indicators on Apache, Black Hawk, Chinook and Kiowa for roughly 20 years; automates vibration checks and rotor track-and-balance, defers replacements to phase maintenance. Estimated savings: ~$9.3M/yr on Apache maintenance test flights, ~$2.6M/yr on UH-60 |
| Ground (Uptake) | 2018 pilot of Uptake's AI on **32 Bradley M2A3s** at Fort Hood ($1M) to predict failing parts. AFRL purchase order (Jan 2025) for CBM+ analytics on JLTV |
| Lesson | HUMS-equipped helicopters are the richest sensor case. For India this means ALH, LCH, Apache and Chinook first |
| Sources | [Army.mil](https://www.army.mil/article/84612/army_developing_new_aircraft_maintenance_technologies_at_research_lab), [DTIC Army CBM effectiveness](https://apps.dtic.mil/sti/html/tr/ADA502155/index.html), [Engadget](https://www.engadget.com/2018-06-26-us-army-ai-vehicle-repairs-bradley.html), [HigherGov](https://www.highergov.com/contract/FA864925P0136) |

### 2.10 United Kingdom

**(a) BAE Systems Typhoon Availability Service: predictive simulation (Lanner WITNESS)**
- BAE models **each Typhoon's operational life**, including maintenance history and mission type and location, to **predict spare-parts consumption and resupply needs before onboard instrumentation signals a need**.
- An Integrated **Typhoon Availability Service Performance Simulation (TPS)** toolset was deployed at RAF Coningsby. It won BAE's Chairman's Award for Innovation in 2011.
- Context: an initial 5-year **£450M** availability contract (2009). Predictive modelling underpins a target of **£2B** savings over the 25-year contract.
- **Lesson:** *A simulation-based "twin" of the support enterprise* tied to an availability contract is a proven concept, though proprietary and contractor-run.
- Sources: [Lanner](https://lanner.com/insights/news/predictive-simulation-guides-fighter-jet-maintenance-for-raf.html), [BAE](https://www.baesystems.com/en/article/a-new-kind-of-flight-simulation), [Lanner award](https://www.lanner.com/insights/news/typhoon-simulation-project-wins-bae-systems-chairmans-award-for-innovation-2011.html)

**(b) DE&S: AI/LLM-assisted Typhoon maintenance optimisation**
- DE&S uses **large language model technology to adjust maintenance procedures** and improve availability. It has identified **~2,500 maintenance hours/year** of savings, with a further **~4,000** projected in phase 2. Part of Typhoon's maintenance-optimisation portfolio.
- Source: [DE&S case study](https://des.mod.uk/what-we-do/defence-experts-case-studies/delivering-change-to-drive-excellence)

**(c) Royal Navy "Motherlode" analytics platform (v3)**
- Built by **1710 Naval Air Squadron** and DE&S's Automation and AI team. Earlier versions supported Merlin, Wildcat, Apache and Chinook. **Version 3 extends to fixed-wing.** It provides **plain-language explanations** alongside technical outputs for flight-line maintainers.
- **Lesson:** in-house military teams can build useful analytics platforms, and explainability for maintainers is a core feature.
- Source: [ePlaneAI](https://www.eplaneai.com/news/royal-navy-extends-ai-predictive-maintenance-to-fixed-wing-aircraft)

### 2.11 France: DMAé and RAVEL (verticalised Rafale support)

- **DMAé** (Direction de la maintenance aéronautique) restructured military aviation support. **RAVEL** ("VErticaLisé RAfale") gave Dassault Aviation responsibility for **all support of the French Rafale** (aircraft and equipment) under a ~10-year contract (2019), with **logistics one-stop shops at home bases** (Landivisiau, Mont-de-Marsan, Saint-Dizier).
- **Lesson:** single-point accountability for availability can work, at the price of contractor dependence. India's Rafale PBL (75% minimum availability) applies the same idea.
- Sources: [Journal de l'Aviation](https://www.journal-aviation.com/en/news/43378-ravel-reconfigures-the-french-rafale-operational-condition-maintenance-ocm), [Dassault 2019 results](https://www.dassault-aviation.com/wp-content/blogs.dir/1/files/2020/02/Dassault-Aviation-2019-FY-Results_English.pdf)

### 2.12 Israel: vision-based prognostics (Odysight.ai)

- Ruggedised miniature cameras in hard-to-reach failure points, with AI detecting cracks, loose parts and abnormal behaviour. Orders: >$1M from an international defence contractor for upgraded **Israeli Air Force SH-60 Seahawks**, and $0.3M via Elbit for the Israeli MoD.
- **Lesson:** new sensing modalities (vision) can retrofit legacy platforms, which is relevant to India's sensor-poor fleets.
- Sources: [GlobeNewswire](https://www.globenewswire.com/de/news-release/2024/03/11/2843783/0/en/Odysight-ai-Announces-Purchase-Order-from-an-International-Defense-Contractor-for-its-Visual-Based-Predictive-Maintenance-System-to-be-Installed-in-an-Upgraded-Israel-Air-Force-IAF.html), [SEC filing](https://www.sec.gov/Archives/edgar/data/1577445/000149315224009491/ex99-1.htm)

### 2.13 Other programmes worth knowing

| Programme | Note | Source |
|---|---|---|
| DIUx (2017): AI predictive maintenance on F-16s | Early DoD commercial-AI pilot | [Defense One](https://www.defenseone.com/defense-systems/2017/11/diux-accelerates-ai-development-for-predictive-maintenance-on-f-16s/191974/) |
| USAF F-16 Phase Maintenance Cycle simulation | Discrete-event simulation to maximise availability (Winter Simulation Conference, 2016) | Winter Simulation Conference proceedings (e.g. [WSC archive](https://www.informs-sim.org/wsc08papers/142.pdf)) |
| Canadian CH-149 Cormorant availability simulation | DES of all maintenance activities found that availability problems could not be solved by fixing spares alone; maintenance structure and basing matter | Winter Simulation Conference literature (verify the exact paper before citing formally) |
| Rapid Sustainment Office "digital binder" | Digital maintenance documentation to cut maintenance time | [AFLCMC](https://www.aflcmc.af.mil/NEWS/Article/4392913/rapid-sustainment-office-demonstrates-new-digital-binder-application-for-reduci/) |
| GE Aerospace + Palantir partnership expansion | Military aviation readiness for the USAF and GE production | Press reports (2025); not independently verified here |

---

## 3. Indian initiatives

| # | Initiative | Owner / partner | Date | What it does | Scope limit | Source |
|---|---|---|---|---|---|---|
| 1 | **e-MMS** (IDM-MAXIMO) | IAF + Wipro (SI) | contract 2013; rolled out ~2016–21 | Maintenance ERP: records, inventory and MRO across 170 bases and 13 BRDs; real-time fleet availability monitoring at hierarchy levels | Records system, not analytics | [GKToday](https://www.gktoday.in/indian-air-forces-electronic-maintenance-management-system-launched/) |
| 2 | **e-MMS Lite** | IAF + Wipro | ~2023 | Mobile field recording of maintenance | Capture only | [defence.in](https://defence.in/threads/iaf-embraces-mobile-maintenance-management-with-e-mms-lite.4325/latest) |
| 3 | **IMMOLS** | IAF + TCS | conceived 1994; live 2006 | Online materials management across 108 sites; e-logistics governance | Inventory transactions | [OneIndia](https://www.oneindia.com/2006/10/09/defence-minister-dedicates-tcs-immol-for-iaf-to-nation-1160400889.html) |
| 4 | **UDAAN AI CoE** | IAF | Jul 2022 | Big Data Analytics and AI platform; applications in supply logistics, intelligence, decision support and training | Platform/CoE, not a maintenance product | [IDR](https://indiandefencereview.com/artificial-intelligence-ai-centre-of-excellence-coe-launched-by-indian-air-force-iaf/) |
| 5 | **IAF–IIT Bombay Su-30MKI predictive maintenance** | IAF + IIT Bombay (C-MInDS, Mechanical Engg.) | 27 May 2026 | Three contracts; indigenous AI model to read a **"health index"** of gas-turbine engines in mid-life maintenance; prognostic and prescriptive maintenance | Su-30 engines first | [IIT Bombay on X](https://x.com/iitbombay/status/2059612674691158121), [SSBCrack](https://www.ssbcrack.com/2026/05/indian-air-force-signs-contracts-with-indian-institute-of-technology-bombay-for-predictive-maintenance-of-su-30-mki-fleet.html), [IDSA brief](https://idsa.in/publisher/issuebrief/from-reactive-repairs-to-predictive-power-an-ai-digital-twin-health-index-for-the-su-30-mki) |
| 6 | **ML-based HUMS for MiG-29K** | DRDO (TDF) + Smart Machines & Structures, Hyderabad | handed over Feb 2023; Navy order | Processes FDR data to flag components likely to fail, with timelines; automates pre-flight checks (saves 10–15 min per flight) | Single naval platform | [Deccan Herald](https://deccanherald.com/amp/city/an-artificial-intelligence-push-to-prediction-of-flight-failures-1191860.html), [Tribune](https://www.tribuneindia.com/news/nation/engines-of-navys-mig-29k-fighter-aircraft-to-be-maintained-using-ai-478868), [idrw](https://idrw.org/tdf-funded-mig-29k-serviceability-software-gets-navy-order/) |
| 7 | **AI-based Snag Disposition Information Management System** | HAL LCA-Tejas Division | Aug 2025 | ML for snag identification, categorisation, tracking and resolution; traceability | Tejas production/maintenance | [Indian Defence News](https://www.indiandefensenews.in/2025/08/hals-tejas-bangalore-unit-develops-ai.html), [idrw](https://idrw.org/?p=381683) |
| 8 | **IAF digital twins, AI and 3D printing for maintenance** | IAF | 2022–2026 | Digital twins to track system condition; in-house 3D additive manufacturing centre (2022) for urgent spares | Not publicly specified | [Usthadian](https://www.usthadian.com/iaf-builds-indigenous-strength-through-a-930-firm-maintenance-network/) |
| 9 | **~180 Make / iDEX / TDF projects** | IAF | ongoing | >₹17,000 crore of business opportunities | Many separate projects | [Adda247](https://currentaffairs.adda247.com/iaf-expands-indigenous-maintenance-network-with-930-indian-firms/) |
| 10 | **930-firm indigenous maintenance network** | IAF | as of 31 Aug 2026 | **62,300+ spare parts** produced domestically; **~97% of frequently used operational spares and ~93% of mandatory overhaul spares** indigenised | Supply side | [Adda247](https://currentaffairs.adda247.com/iaf-expands-indigenous-maintenance-network-with-930-indian-firms/) |
| 11 | **HQ Maintenance Command indigenisation** | IAF HQMC | 2022–2023 | >60,000 lines indigenised; ₹800 crore saved; 5-year plan with ₹10,500 crore outflow to Indian industry; ~3,000 components indigenised after the Ukraine war (₹160 crore forex saved, Jan 2022–Jun 2023) | Supply side | [Tribune](https://www.tribuneindia.com/news/chandigarh/iaf-saved-160-cr-by-indigenising-spares-after-russia-ukraine-war-567972), [Hitavada](https://www.thehitavada.com/Encyc/2023/7/21/IAF-Maintenance-Command-draws-up-5-year-plan-for-30-self-reliance-projects.html) |
| 12 | **Sankalp-2026** compendium | IAF | Aug 2026 | Problem statements for indigenisation; priority on sustaining Su-30MKI and MiG-29; replace Russian avionics and radar; **Plant-in-Plant** private cells inside BRDs | Industrial policy | [Indian Defence News](https://www.indiandefensenews.in/2026/08/indian-air-force-launches-sankalp-2026.html), [Devdiscourse](https://www.devdiscourse.com/article/law-order/3957290-sankalp-2026-showcases-indias-push-for-self-reliant-defence-aviation) |
| 13 | **SRIJAN portal / Positive Indigenisation Lists** | MoD DDP | 2020–2026 | 33,000+ items offered; 5,012 items across the first 5 PILs; 6th PIL (Aug 2026) adds 405 items worth ₹3,070 crore; 15,700+ indigenised; ~₹9,000 crore import substitution | Catalogue, not readiness-weighted | [Outlook](https://outlookindia.com/national/defence-ministry-notifies-6th-indigenisation-list-of-405-items-including-advanced-helicopters-worth-rs-3070-crore) |
| 14 | **Navy iDEX AI-based Condition-Based Predictive Maintenance (CBPM)** | Indian Navy / iDEX | DISC | Winners: Edgeforce Solutions (Hyderabad), Guardinger Advanced Technologies (Pune) | Naval machinery | [iDEX](https://idex.gov.in/disc-category/5) |
| 15 | **BEL AI-based predictive maintenance for fire-control systems**; BEL AI incubation with the Army | BEL | 2023–25 | Predictive maintenance for ground systems | Not aviation fleets | [DSIJ](https://insights.dsij.in/dsijarticledetail/how-indian-defence-companies-are-harnessing-ai-for-modern-warfare-id011) |
| 16 | **DRDO CAIR "75+ AI products"** | DRDO | — | Broad AI portfolio | General | [DSIJ](https://insights.dsij.in/dsijarticledetail/how-indian-defence-companies-are-harnessing-ai-for-modern-warfare-id011) |
| 17 | **ETAI Framework** | DRDO SAG | Oct 2024 | Risk-based trustworthy-AI evaluation with 5 principles | Governance | [IndiaAI](https://indiaai.gov.in/news/trustworthy-ai-framework-launched-for-critical-defence-operations) |
| 18 | **DPM 2025** | MoD | Sep 2025 | Faster revenue procurement; 15% upfront growth provision for aerial/naval repairs and refits | Process | [Outlook Business](https://www.outlookbusiness.com/news/defence-ministry-unveils-new-framework-to-streamline-revenue-procurement) |
| 19 | **Ramco Aviation software for the Tata C-130J MRO** | Ramco Systems (Chennai) + Tata Advanced Systems | 2024–25 | Aviation MRO ERP for the IAF C-130J MRO facility; ML suggests similar past defects; also supports GA-ASI MQ-9B MRO | One MRO site | [IT Brief](https://itbrief.co.nz/story/ramco-wins-tata-defence-mro-deal-for-c130j-maintenance) |
| 20 | **Rafale PBL** | IAF + Dassault/Safran | 2016 onwards | 75% minimum availability; M88 MRO in Hyderabad (~2027) | One fleet | [Defence Security Asia](https://defencesecurityasia.com/en/india-rafale-french-support-deal-indo-pacific-airpower-balance/) |

**Think-tank / opinion inputs**
- **MP-IDSA Issue Brief (Wg Cdr Anamika Choudhary, 1 Jul 2026):** argues for an AI digital-twin "health index" for the Su-30MKI. Its value "will depend on **data integrity, cyber hardening, and timely project completion**". ([IDSA](https://idsa.in/publisher/issuebrief/from-reactive-repairs-to-predictive-power-an-ai-digital-twin-health-index-for-the-su-30-mki))
- **The Week opinion (Kalyanjit Hatibaruah, 3 Aug 2026):** describes the IAF's move to predictive maintenance with big data and ML, digital twins, and **Edge AI at forward bases** for local processing. 🟠 Opinion piece; treat as indicative. ([The Week](https://www.theweek.in/news/defence/2026/08/03/opinion-or-keeping-iafs-sukhoi-and-tejas-fleets-combat-ready-with-machine-learning.html))
- **CAPS (2026)**, **ORF (2026)**, **Carnegie (Oct 2025)**: sustainment lessons from Operation Sindoor and the IAF's fighter depletion. ([ORF](https://www.orfonline.org/expert-speak/the-multiple-travails-of-the-iaf-india-s-fighter-strength-depletion), [Carnegie](https://carnegieendowment.org/research/2025/10/military-lessons-from-operation-sindoor))

---

## 4. Commercial platforms and products

### 4.1 C3 AI Readiness (and the C3 AI platform behind PANDA)
- AI predictive-maintenance application that fuses **sensor, maintenance and parts data**. It **updates part-demand forecasts dynamically** from predictive-maintenance and MTBF modules as conditions and mission profiles change.
- Features: failure-mode identification; **evidence packages**; case management; automated maintenance verification; generative-AI conversational search; codified SME knowledge.
- Vendor claims: **5+ months** alert-to-failure lead time, **95%** real-world alert precision, **7×** faster root-cause analysis.
- Sources: [C3 AI Readiness](https://c3.ai/products/c3-ai-readiness-product/), [datasheet](https://c3.ai/wp-content/uploads/2025/03/C3-AI-Data-Sheet-Readiness.pdf)

### 4.2 Airbus Skywise (civil) and SmartForce (military)
- **Skywise** (with Palantir, launched 2017): an open aviation data platform connecting **10,000+ aircraft** and **100+ airlines**. Used for event tracking, turnaround analysis, predictive maintenance, reliability analysis and benchmarking, and maintenance decision support. Third-party estimates put the cost-saving potential above $1.7B/yr.
- **SmartForce** (launched Jul 2018): the military counterpart for **NH90, A400M, A330 MRTT**, covering troubleshooting, maintenance optimisation, predictive solutions and demand planning. Security features include **geographic isolation, accredited personnel and monitoring by national cyber authorities**.
- **Lesson:** a military variant must be *sovereign-hosted*. India would need an equivalent that is fully indigenous and on-premise.
- Sources: [Airbus SmartForce PR](https://www.airbus.com/en/newsroom/press-releases/2018-07-airbus-launches-smartforce-services-bringing-the-power-of-data-to), [Airbus SmartForce page](https://airbus.com/en/products-services/defence/military-aircraft/military-aircraft-services/smartforce), [Aviation Week on Skywise](https://aviationweek.com/aerospace/emerging-technologies/airbus-launches-new-open-aviation-data-platform-support-digital), [HBS case](https://d3.harvard.edu/platform-digit/?p=9858)

### 4.3 Palantir (Foundry; Skywise; GE Aerospace partnership)
- Foundry is the data-integration and ontology platform under Skywise. Palantir also supplies US Army logistics and supply-chain applications, and has an expanded partnership with GE Aerospace for USAF readiness.
- **Lesson:** an **ontology** (object model of aircraft, parts, events, agencies) is the backbone of integration.
- Sources: [Palantir 10-K](https://www.sec.gov/Archives/edgar/data/1321655/000132165523000011/pltr-20221231.htm), [Palantir logistics brief](https://www.palantir.com/assets/xrfr7uokpv1b/7Ih1pWFovgfKvkUOajdcrY/953263eb9d42eee9c4734f518b4ebab4/AUSA_Logistics___Supply_Chain__1_.pdf)

### 4.4 Boeing Global Services: AnalytX and Readiness Operations Centers
- **AnalytX** brings together 800+ analytics experts. **Boeing Readiness Operations Center** supports F-15, F/A-18, KC-46, AH-64, CH-47 and C-17 by integrating health systems and analytics. The **V-22 Readiness Operations Center** works under PBL with predictive and condition-based maintenance.
- Sources: [Boeing ROC PR](https://boeing.mediaroom.com/Boeing-Readiness-Operations-Center-Launches-to-Improve-Performance-for-Global-Defense-Operations?asPDF=1), [Bell-Boeing V-22](https://boeing.mediaroom.com/2019-01-18-Bell-Boeing-awarded-144-million-for-V-22-support?asPDF=1), [Aviation Today](https://www.aviationtoday.com/2017/06/19/boeing-unveils-data-analytics-division-5-agreements/)

### 4.5 Lufthansa Technik AVIATAR
- Airline platform covering condition monitoring, **predictive health analytics**, **reliability management** (automated reliability reports), technical logbook and MRO management. It converts unscheduled maintenance into planned interventions.
- Sources: [Aviation Today 2016](https://www.aviationtoday.com/2016/10/19/lufthansa-launches-predictive-maintenance-platform/), [IATA SWISS case](https://www.iata.org/contentassets/f03b1a4b79534b99802f10cd23b19ec2/1430-1500-aviatar-platform-swiss.pdf)

### 4.6 IFS Maintenix for Defense (formerly Mxi)
- Military aviation maintenance management for distributed networks, aiming to maximise lifecycle availability, optimise downtime and ensure compliance. Used by several air forces.
- Source: [IFS Maintenix for Defense](https://www.ifs.com/it/assets/2022/02/22/ifs-maintenix-for-defense)

### 4.7 Ramco Aviation (Indian vendor)
- Chennai-based aviation MRO/M&E ERP with AI-powered scheduling, predictive tasks, and ML that suggests **similar past defects**. Ramco has published on **rogue-component monitoring**. Defence references: Tata Advanced Systems C-130J MRO (IAF fleet), GA-ASI MQ-9B MRO.
- Sources: [Ramco defence](https://www.ramco.com/products/aviation-software/defense-industry), [Ramco rogue blog](https://www.ramco.com/blog/monitoring-rogue-aircraft-component-reliability), [ADU interview](https://aviation-defence-universe.com/ramco-systems-ceo-a-ab-on-aviation-software-6-0-and-the-future-of-mro-technology)

### 4.8 IBM Maximo
- The asset-management suite on which the IAF's e-MMS (IDM-MAXIMO) is built. Maximo APM adds predictive and health modules in its commercial form.
- Relevance: NIRANTAR should **integrate with Maximo-based data structures** rather than replace them.

### 4.9 Systecon Opus Suite (OPUS10, SIMLOX, CATLOC)
- **OPUS10:** multi-echelon, multi-indenture spares optimisation and logistics support analysis (LSA); cost-effectiveness curves; LCC.
- **SIMLOX:** event-driven simulation of operational availability over time under varying operations and support scenarios, which **reveals weaknesses during peak utilisation**.
- **CATLOC:** life-cycle cost analysis.
- Users include the US DoD (e.g. the Navy Common Readiness Model; F-35 what-if stress tests) and many European forces (e.g. a Swedish NH90 case study).
- **Lesson:** the "availability simulation + spares optimisation" combination exists commercially (Swedish IP, licensed). India would want a sovereign equivalent coupled to live predictive data.
- Sources: [NPS SYM-AM-23-147](https://dair.nps.edu/bitstream/123456789/4914/1/SYM-AM-23-147.pdf), [NPS SYM-AM-25-426](https://dair.nps.edu/bitstream/123456789/5437/1/SYM-AM-25-426.pdf), [Swedish NH90 case](https://ftfsweden.se/wp-content/uploads/2016/11/FT2016_M06_Johan_Elfvik_Case-study-Swedish-NH90.pdf), [WSC 2020](https://informs-sim.org/wsc20papers/215.pdf)

### 4.10 Lanner (now part of Haskoning) WITNESS: predictive simulation
- Discrete-event simulation used by BAE for Typhoon availability (see 2.10a).
- Source: [Haskoning](https://www.haskoning.com/en/markets/digital-solutions/predictive-simulation/aerospace)

### 4.11 Engine-OEM health monitoring (general)
- Engine makers (Rolls-Royce, GE Aerospace, Pratt & Whitney, Safran) run engine-health-monitoring and digital-twin services, usually within "power-by-the-hour" or PBL contracts. They focus on engines; data rights usually stay with the OEM.
- **Lesson for India:** for imported engines (AL-31FP, RD-33, F404, M88, Adour) the OEM may not share models. India needs *its own* engine-health capability, which is what IIT Bombay is building for the AL-31FP.

### 4.12 Other relevant vendors (non-exhaustive)
- **Uptake** (industrial AI; US Army pilots), **Odysight.ai** (vision PHM), **Honeywell Forge** and **Collins Ascentia** (connected-aircraft analytics), **SITA/airline MRO analytics**, **Aerogility** (agent-based MRO planning simulation), **Simio / Arena** (simulation engines used for readiness studies, e.g. [Rockwell Arena equipment-readiness case](https://www.rockwellautomation.com/en-au/products/software/arena-simulation/case-studies/equipment-readiness-availability.html)).

---

## 5. Academic research streams

### 5.1 Remaining Useful Life (RUL) prediction on benchmarks
- **The dominant stream.** Thousands of papers use **NASA C-MAPSS** (FD001–FD004) and, since 2021, **N-CMAPSS**. Methods include LSTM/Bi-LSTM, CNN, Transformers, GNNs, contrastive learning, mixers and Gaussian processes. Examples:
  - Stacked deep CNN for turbofan RUL ([arXiv 2111.12689](https://arxiv.org/pdf/2111.12689))
  - Supervised contrastive dual-mixer model ([arXiv 2401.16462](https://arxiv.org/pdf/2401.16462))
  - Embedded ConvLSTM framework ([arXiv 2008.03961](https://arxiv.org/pdf/2008.03961))
  - Trend-feature RNN ([arXiv 2112.05372](https://arxiv.org/pdf/2112.05372))
  - GNN survey for RUL ([arXiv 2409.19629](https://arxiv.org/pdf/2409.19629))
  - Functional data analysis RUL ([arXiv 1904.06442](https://arxiv.org/pdf/1904.06442))
  - Eventual-failure prediction + RUL ([arXiv 2303.12982](https://arxiv.org/pdf/2303.12982))
  - Hybrid GPR with temporal features for interval RUL ([arXiv 2411.15185](https://arxiv.org/pdf/2411.15185))
- **Limitation:** simulated data, single-component focus, point accuracy (RMSE) instead of decision value. **This is where most SIH teams stop.**

### 5.2 Uncertainty quantification and conformal prediction
- Conformal prediction intervals for RUL with **formal coverage guarantees** (C-MAPSS with CNN and GBM) ([arXiv 2212.14612](https://arxiv.org/pdf/2212.14612); [IJPHM](https://papers.phmsociety.org/index.php/ijphm/article/view/3417)); distribution-free intervals ([PHM Conf](https://papers.phmsociety.org/index.php/phmconf/article/view/2249)); conformalised quantile regression with aerospace risk preferences (2026); multi-fidelity fusion with conformal intervals for dormant components ([Aerospace 2026](https://www.citedrive.com/en/discovery/empirically-calibrated-multi-fidelity-fusion-with-conformal-prediction-intervals-for-reliability-assessment-of-aerospace-dormant-components/)).
- **Relevance:** calibrated intervals are a prerequisite for decision-making and trust.

### 5.3 Prognostics → spares and maintenance joint optimisation
- Integrating RUL prognostics with **limited stocks of repairable spares and shared maintenance slots** for an aircraft fleet (cooling-system case). Joint optimisation of inspection and spare provisioning under Wiener degradation. Integrated condition-based replacement and ordering. A metric-driven framework for evaluating prognostic-based failure estimates on spare-part inventory management ([PHME](https://papers.phmsociety.org/index.php/phme/article/view/4942); [RESS 2021](https://ideas.repec.org/a/eee/reensy/v214y2021ics095183202100288x.html); [JSEE 2017](https://www.jseepub.com/EN/Y2017/V28/I6/1133); [Georgia Tech PAIS](https://pais.scl.gatech.edu/node/4)).
- **Key insight from this literature:** *"Separately optimising MRO and spare part logistics always yields either excessive overstocking and obsolescence or mission-critical stockouts."*
- **Limitation:** mostly single-echelon, single-fleet, stylised models. Not deployed at national scale. No geopolitics.

### 5.4 Fleet-level condition-based maintenance and data fusion
- Data fusion for optimal condition-based aircraft fleet maintenance ([ISIF 2024](https://isif.org/files/isif/2024-04/06-102022-0013R1.pdf)); rare-failure prediction via event matching for aerospace ([arXiv 1905.11586](https://arxiv.org/pdf/1905.11586)); defence-industry PdM framework from a digital-twin perspective ([Measurement 2026](https://www.sciencedirect.com/science/article/abs/pii/S0263224126011450)).

### 5.5 Federated learning for prognostics
- **Federated RUL prognostics across airlines** without sharing raw data, with decentralised validation and robust aggregation against noisy data ([arXiv 2506.00499](https://arxiv.org/abs/2506.00499)); Cambridge "Federated Learning for Collaborative Prognosis" ([repository](https://www.repository.cam.ac.uk/handle/1810/303500)); federated fleet learning with XAI (2026); dynamic FL across multi-domain environments ([UvA](https://www.dare.uva.nl/id/9f23aa85-e607-4484-b549-6c8b7fbcac34)).
- **Relevance:** the technique exists. *Applying it across India's services* (IAF/Navy/Army/CG/HAL on common types) does not.

### 5.6 Rogue components, NFF and repair effectiveness
- **Rogue components:** a small subset of a repairable population that develops failure modes outside standard repair procedures. A common industry definition is **≥3 removals of the same serial for similar discrepancies, or 4 NFF removals in 12 months**. Logical Analysis of Data (LAD) has been applied to detect rogues among airline turbo-compressors ([J. Intelligent Manufacturing](https://link.springer.com/article/10.1007/s10845-009-0351-1)).
- **No Fault Found** research in the RAF ([Cranfield](https://dspace.lib.cranfield.ac.uk/handle/1826/11741)); component NFF ([AviationPros](https://www.aviationpros.com/home/article/10388028/component-no-fault-found)); NAVAIR "Y-coded WRAs" (repeat offenders) and **bad-actor processing** on Integrated Test Benches ([NDIA](https://ndia.dtic.mil/wp-content/uploads/2008/systems/7580birurakis.pdf)); fleet performance optimisation patents ([USPTO 9327846](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9327846)); HUMS 2019 paper ([Baker](https://humsconference.com.au/Papers2019/Peer_Reviewed/HUMS2019_Baker.pdf)).
- **Imperfect repair theory:** the **Generalized Renewal Process (Kijima virtual age)** estimates a repair-effectiveness factor *q* (0 = good-as-new, 1 = same-as-old) ([Wikipedia](https://en.wikipedia.org/wiki/Generalized_renewal_process); [arXiv 1006.3718](https://arxiv.org/pdf/1006.3718)).
- **Relevance:** rogue detection exists in airline practice and products (Ramco, airline reliability programmes). **Estimating repair effectiveness per *repair agency* and routing work accordingly is not reported in the public literature for military fleets.**

### 5.7 Maintenance-text NLP
- **MaintNet** (RIT; COLING/AACL 2020): open logbook data for aviation, automotive and facilities, with tools for abbreviations, non-standard spelling and clustering ([arXiv 2005.12443](https://arxiv.org/pdf/2005.12443); [ACL demo](https://preview.aclanthology.org/fix-dup-bibkey/2020.aacl-demo.5)).
- Commercial LLM use: DE&S Typhoon (LLM-assisted procedure optimisation), C3 Generative AI, HAL's AI snag system.

### 5.8 Predictive maintenance on real flight data
- **NGAFID Maintenance Classification (NGAFID-MC)**: 7,500+ labelled flights, 11,500+ hours of 23-parameter per-second FDR data before/after unplanned maintenance. The larger set has 31,177 hours, 28,935 flights and 2,111 maintenance events in 36 issue types. A **Convolutional Multi-Headed Self-Attention** model outperforms RNNs ([AAAI 2022](https://ojs.aaai.org/index.php/AAAI/article/view/21538); [arXiv 2210.07317](https://arxiv.org/abs/2210.07317v1)).

### 5.9 Digital-twin reviews
- Requirement-based roadmap for standardised PdM automation with digital twins ([arXiv 2311.06993](https://arxiv.org/pdf/2311.06993)); systematic review of DT-driven PdM taxonomy ([arXiv 2509.24443](https://arxiv.org/pdf/2509.24443)); the DT landscape at the crossroads of PdM, ML and physics-based modelling ([arXiv 2206.10462](https://arxiv.org/pdf/2206.10462)); DT feedback for PdM in IIoT ([Research Square](https://assets-eu.researchsquare.com/files/rs-10366707/v1_covered_ea477a51-6f75-486b-bb1f-97adfad576b6.pdf)).

### 5.10 Signal detection in safety reporting (cross-domain)
- **Pharmacovigilance disproportionality analysis**: PRR, ROR, BCPNN and Gamma-Poisson Shrinker detect emerging adverse-event signals in spontaneous reports (WHO/EMA practice) ([PMC8193489](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8193489/); [EMA guideline](https://eudravigilance.ema.europa.eu/human/docs/26June08-GL%20on%20the%20use%20of%20stat%20meths%20signal%20detection%20EVDAS.pdf)).
- **Our search did not find these methods applied systematically to military maintenance/defect reports for cross-fleet early warning.** This gap is exploited in Document 3.

---

## 6. Open datasets

| Dataset | Domain | Content | Use in a prototype | Link |
|---|---|---|---|---|
| **NASA C-MAPSS** (FD001–FD004) | Turbofan simulation | Run-to-failure trajectories; 21 sensors; 3 operating settings; 1–6 conditions; 1–2 fault modes | Engine RUL baseline | [NASA PCoE](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) |
| **NASA N-CMAPSS** (Arias Chao et al., 2021) | Turbofan, realistic flights | Full flights (climb/cruise/descent); 7 failure modes across fan, LPC, HPC, LPT, HPT; PHM 2021 Data Challenge | Better engine RUL, operation-dependent degradation | [MDPI Data 6(1):5](https://mdpi.com/2306-5729/6/1/5); [PHM 2021](https://data.phmsociety.org/wp-content/uploads/sites/9/2021/08/2021_Data_Challenge.pdf) |
| **NGAFID-MC** | General-aviation FDR + maintenance | 7.5k labelled flights; 23 sensors; before/after maintenance | Real-flight-data maintenance classification | [arXiv 2210.07317](https://arxiv.org/abs/2210.07317v1) |
| **MaintNet** | Maintenance logbooks | Aviation/automotive/facility logbook text and tools | Snag-text NLP | [arXiv 2005.12443](https://arxiv.org/pdf/2005.12443) |
| **FAA SDRS** (Service Difficulty Reports) | Real defect reports | Annual CSVs: aircraft type, total time/cycles, **part number and serial**, ATA chapter, 750-char description, discovery circumstances, action | Rogue detection, signal detection, removal statistics | [FAA SDR download](https://www.faa.gov/av-info/download_SDR) |
| **NASA DASHlink Sample Flight Data** | Regional-jet FDR | ~186 parameters; per-tail datasets; multi-year commercial ops; a ~99k-flight approach subset | Usage spectra, anomaly detection, flight-data pipelines | [DASHlink](https://c3.ndc.nasa.gov/dashlink/projects/85); [data.gov tail 687 etc.](https://catalog.data.gov/dataset/flight-data-for-tail-670) |
| **HUMS2023 Data Challenge** (DSTG Australia) | Helicopter gearbox | Bell 206B-1 (OH-58) main rotor gearbox planet-gear rim crack propagation; 526 MATLAB files of 4-channel hunting-tooth averages; extended set released Jul 2023 | Helicopter HUMS diagnostics/prognostics (ALH-style use case) | [Dataset description](https://www.humsconference.com.au/HUMS2023/HUMS2023_Data_Challenge_dataset_description_v1.1.1.pdf); [challenge](https://humsconference.com.au/HUMS2023datachallenge/) |
| **Airbus Helicopter Accelerometer Dataset** (ETH Zurich) | Helicopter vibration | 1,677 normal 1-minute sequences (train), 594 test (297 anomalous), 1024 Hz | Unsupervised vibration anomaly detection | [ETH Research Collection](https://research-collection.ethz.ch/handle/20.500.11850/415151) |
| **PHM Society data challenges** (2008–2025) | Various | Bearings, gearboxes, engines, etc. | Method benchmarking | [PHM Society](https://data.phmsociety.org/) |
| **NASA PCoE repository** | Various | Batteries, bearings (IMS), milling, CFRP, etc. | Component prognostics | [NASA PCoE](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) |
| **Public overview of PHM degradation datasets** | Meta | Survey of datasets by task | Picking datasets | [Moonlight review](https://themoonlight.io/fr/review/overview-of-publicly-available-degradation-data-sets-for-tasks-within-prognostics-and-health-management) |
| **Live public ops data** (ADS-B, METAR) | Ops and weather | Used by the READYFLEET SIH team | Environment covariates (weather/salinity proxies) | [adsb.lol](https://adsb.lol), [AWC](https://aviationweather.gov) |

**What no public dataset provides:** military *multi-agency* records, repair-agency turnaround and quality, spares lead times under sanctions, or cross-service common-type histories. These must be **synthesised realistically** for any prototype (see Document 3).

---

## 7. Open-source software and GitHub repositories

### 7.1 Prognostics and health management

| Repo / package | What | Notes | Link |
|---|---|---|---|
| **NASA ProgPy** (prog_models + prog_algs + prog_server) | Python framework for prognostics models, state estimation (UKF, particle filter) and prediction with uncertainty propagation | **NASA Software of the Year 2024**; `pip install progpy` | [github.com/nasa/progpy](https://www.github.com/nasa/progpy), [prog_models](https://github.com/nasa/prog_models), [JOSS paper](https://www.theoj.org/joss-papers/joss.05099/10.21105.joss.05099.pdf) |
| **biswajitsahoo1111/rul_codes_open** | Reproducible RUL ML/DL notebooks on public datasets | ~218★ (Apr 2026), MIT | [repo](https://github.com/biswajitsahoo1111/rul_codes_open) |
| **umbertogriffo/Predictive-Maintenance-using-LSTM** | LSTM regression and classification on turbofan data (MAE ≈12 cycles; classification F1 ≈0.96) | ~737★, cited in textbooks | [repo](https://github.com/umbertogriffo/Predictive-Maintenance-using-LSTM) |
| **archd3sai/Predictive-Maintenance-of-Aircraft-Engine** | Multiple PdM techniques on turbofan data | Popular tutorial | [repo](https://github.com/archd3sai/Predictive-Maintenance-of-Aircraft-Engine) |
| **ozogxyz/cmapss** | Novel algorithms for C-MAPSS RUL | Research | [repo](https://github.com/ozogxyz/cmapss) |
| **mohyunho/N-CMAPSS_DL** | Data preparation for N-CMAPSS | Loader | [repo](https://github.com/mohyunho/N-CMAPSS_DL) |
| **kokikwbt/predictive-maintenance (PdMData)** | Unified dataset loaders, tasks and scoring protocols for PdM | Toolkit | [repo](https://github.com/kokikwbt/predictive-maintenance) |
| **camillecochener/Anomaly-detection-of-accelerometers-data** | Airbus helicopter accelerometer anomaly detection | Example | [repo](https://github.com/camillecochener/Anomaly-detection-of-accelerometers-data) |
| **ritu-thombre99/rul-prediction** and the *rul-prediction* topic | Many C-MAPSS RUL projects | Index | [topic](https://repos.ecosyste.ms/topics/rul-prediction) |

### 7.2 Reliability, survival and repairable systems

| Package | What | Link |
|---|---|---|
| **reliability** (Matthew Reid) | Weibull/lognormal/gamma fitting with censoring, mixture models, ALT, stress–strength, probability plots; Reliasoft/Minitab-like | [PyPI](https://pypi.org/project/reliability/), [docs](https://reliability.readthedocs.io/) |
| **lifelines** (Cam Davidson-Pilon) | Survival analysis: Kaplan–Meier, Cox PH, AFT, time-varying covariates | [GitHub](https://github.com/CamDavidsonPilon/lifelines) |
| **scikit-survival** | Survival ML: random survival forests, gradient-boosted survival | [GitHub](https://github.com/sebp/scikit-survival) |
| **PyMC / Stan / NumPyro** | Bayesian hierarchical modelling (pooled Weibull across bases/types) | [PyMC](https://github.com/pymc-devs/pymc), [Stan](https://mc-stan.org) |
| GRP / Kijima calculators | Imperfect-repair modelling references | [MetricGate](https://metricgate.com/docs/generalized-renewal-process-kijima/) |

### 7.3 Spares and supply-chain optimisation

| Repo | What | Link |
|---|---|---|
| **jto888/xmetric** (fork: Reliability/xmetric) | **R** package implementing Kettelle, marginal analysis, METRIC, VARI-METRIC and MOD-METRIC for multi-echelon spares (educational) | [repo](https://github.com/jto888/xmetric), [R-forge](https://r-forge.r-project.org/projects/xmetric/) |
| MetricGate METRIC calculator | Web calculator for multi-echelon repairables | [MetricGate](https://metricgate.com/calculator/metric-multi-echelon-repairable) |
| **Google OR-Tools**, **Pyomo**, **PuLP**, **HiGHS** | MILP/CP-SAT for scheduling and allocation | [OR-Tools](https://github.com/google/or-tools), [Pyomo](https://github.com/Pyomo/pyomo), [HiGHS](https://github.com/ERGO-Code/HiGHS) |

### 7.4 Simulation

| Tool | Use | Link |
|---|---|---|
| **SimPy** | Python discrete-event simulation (fleet, depots, pipelines) | [SimPy](https://simpy.readthedocs.io) |
| **Ciw**, **salabim** | Queueing-network / DES alternatives | [Ciw](https://github.com/CiwPython/Ciw), [salabim](https://github.com/salabim/salabim) |
| **Mesa** | Agent-based modelling | [Mesa](https://github.com/projectmesa/mesa) |

### 7.5 Time series, anomaly detection and ML

| Tool | Use |
|---|---|
| **PyOD**, **ADTK**, **Merlion** (Salesforce), **Kats** (Meta) | Anomaly and change detection |
| **tsfresh**, **sktime**, **Darts**, **GluonTS** | Time-series features and forecasting |
| Time-series foundation models (e.g. **Chronos**, **TimesFM**, **MOMENT**) | Zero/few-shot forecasting; offline-hostable weights |
| **MAPIE**, **crepes** | Conformal prediction in Python |
| **SHAP**, **Captum** | Explainability |

### 7.6 Data quality, lineage and MLOps

| Tool | Use |
|---|---|
| **Great Expectations**, **Pandera**, **Soda Core**, **Deequ** | Data validation and quality checks |
| **OpenLineage / Marquez** | Data lineage |
| **DVC**, **MLflow** | Data/model versioning, experiment tracking, model registry |
| **Splink**, **dedupe**, **recordlinkage** | Entity resolution / record linkage (part numbers, serials across systems) |

### 7.7 Digital-twin and IoT frameworks

| Tool | Use |
|---|---|
| **Eclipse Ditto** | Digital-twin state management |
| **Eclipse BaSyx** (Asset Administration Shell) | Industry 4.0 twin standard |
| **Apache Kafka / Redpanda**, **MQTT (Mosquitto)** | Event streaming |
| **TimescaleDB**, **Apache IoTDB** | Time-series storage |

### 7.8 Offline language and speech AI (Indian languages)

| Tool | Use | Link |
|---|---|---|
| **AI4Bharat IndicConformer** (600M multilingual; per-language 120M models; MIT) | Offline speech-to-text for 22 Indian languages; GGUF builds for offline C++ use | [AIKosh](https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicconformer.html), [HF GGUF](https://huggingface.co/Singla0009/IndicConformer-GGUF) |
| **VEXYL-STT** | Self-hosted Indic STT server wrapper | [Medium](https://medium.com/@anilmathewm/vexyl-stt-free-self-hosted-indian-language-speech-to-text-server-f2909003aaf6) |
| **llama.cpp / vLLM / Ollama** | Offline LLM serving | — |
| **FAISS / pgvector** | Vector search for RAG over manuals | — |

### 7.9 Tamper-evidence and transparency logs

| Tool | Use |
|---|---|
| **Sigstore Rekor**, **Google Trillian** | Verifiable append-only (Merkle) logs |
| **libsodium / PyNaCl** (Ed25519) | Signatures |
| **Hyperledger Fabric** | Permissioned ledger (heavier) |

### 7.10 Open MRO / logbook tools

| Tool | What | Link |
|---|---|---|
| **MyTailLog** | Open-source GA logbook digitiser and maintenance tracker (AI reads paper logbooks) | [trendshift](https://trendshift.io/repositories/76691) |
| **Flight MX** (Odoo module, smartops-aero) | Aircraft maintenance tracking and compliance on Odoo | [Odoo apps](https://apps.odoo.com/apps/modules/18.0/flight_mx) |
| **openMAINT** | Open-source CMMS (facilities; adaptable) | [openMAINT](https://www.openmaint.org) |

---

## 8. SIH 2026 (PS SIH26249) team solutions on GitHub

Each publicly visible team repository for the same problem statement is summarised below in detail. **This is the "competition".** NIRANTAR must stand clearly apart from it.

### 8.1 AERO-READY: satyaganesh35/aero-ready
- **Pitch:** moves from "Which aircraft may fail?" to "What maintenance action, when, with what resources, with what effect on fleet availability, and what contingency if constraints change?"
- **Workflow:** *Predict → Explain → Simulate → Optimise → Forecast.*
- **Differentiators claimed:** (1) multi-source fusion of telemetry, logs and inventory; (2) **mission-aware prioritisation** (degradation vs sortie criticality); (3) **graph-based impact propagation** (component → subsystem → aircraft → facilities → fleet) with NetworkX; (4) prescriptive work orders, spares, bay allocation and labour; (5) interactive what-if re-optimisation; (6) SHAP explanations and a RAG copilot citing Technical Orders.
- **Architecture:** a nine-layer system: ingestion (sensors, logs, spares, mission rosters); AI engine (Autoencoder/Isolation Forest anomalies; LightGBM 50-hour failure probability; Bi-LSTM RUL; health index); digital twin and dependency graph (state machine, rainflow fatigue); fleet and logistics optimisation (**Poisson spare-demand**, **PuLP MILP scheduling** with bays, labour and missions); operations UI (what-if, 30-day availability forecast, RAG copilot).
- **Maths:** composite Health Index (0–100); **Mission-Aware Maintenance Priority Index (MAMPI)**; rainflow counting; Brayton-cycle residuals.
- **Stack:** React 19/TS/Tailwind/Recharts; FastAPI; TimescaleDB (PG16) + Redis; scikit-learn, LightGBM, PyTorch; SHAP; NetworkX, PuLP, OR-Tools; LangChain + FAISS/pgvector + Sentence-Transformers + quantised LLM; Docker.
- **Data:** C-MAPSS, synthetic telemetry/logs/spares, synthetic manuals for RAG.
- **Demo:** aircraft A07 shows vibration 3.8 mm/s and ΔEGT +34 °C, giving 88% anomaly confidence, 79% 50-hour risk and 16.4 h RUL. A QRA patrol is due in 14 h, a spare is in stock, and the MILP swaps in A03; the commander approves.
- **Governance:** RBAC, JWT, human authorisation, no flight-control/weapons integration.
- Link: [github.com/satyaganesh35/aero-ready](https://github.com/satyaganesh35/aero-ready)

### 8.2 PREDIX: ans-data-codes/predix-aircraft-predictive-maintenance
- **Capabilities:** forecast degradation, RUL, anomalies/emerging risk, prioritised recommendations, fleet readiness metrics.
- **Architecture:** four pipelines: data (ingest/validate/clean/features) → RUL (health/risk scores) → maintenance decision (risk evaluation, recommendations) → fleet availability (risk ranking, readiness).
- **Data:** C-MAPSS + synthetic health/maintenance/inventory.
- **Stack:** Python, pandas, numpy, scikit-learn, XGBoost, LightGBM, Streamlit, Plotly, joblib.
- **Status:** architecture scaffold. Model training, business rules, dashboards and an LLM agent are still pending.
- Link: [github.com/ans-data-codes/predix-aircraft-predictive-maintenance](https://github.com/ans-data-codes/predix-aircraft-predictive-maintenance)

### 8.3 Fleet Digital Twin: SamruddhiMahajan1/predictive-aircraft-maintenance
- **Question answered:** "Which aircraft cannot fly next week, and why?" for an **8-aircraft fighter fleet**.
- **Mechanics:** every 1.2 s each aircraft advances one C-MAPSS cycle; **XGBoost** runs over 30 cycles × 20+ sensors; RUL is derived; **8 deterministic business rules** (rules 19–26: risk bands >0.70/>0.40; worst part; mission-ready = RUL > 30 and all parts above watch; do-by = RUL − 10; weakest component; back-in-service = free slot + turnaround + lead time if not stocked; spare selection; RUL cap 125); WebSocket push.
- **Engineering quality:** modular monolith behind an nginx BFF; FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16 (20 tables, 33 indexes); `domain/` pure functions with mypy --strict; a **deterministic fallback** `rul = 125 − cycle` reported as "degraded" in `/healthz`; offline-first; one transaction per tick; audit log with JSON diffs; **408 tests**; performance budgets in CI.
- **UI:** React + three.js **3D Rafale model** with five inspectable subsystems (engine, radar, gear, hydraulics, fuel) and damage shading; heatmap; alerts; maintenance plan with look-ahead slider.
- **Data:** C-MAPSS FD001–FD004 (pooled model with per-regime z-score); 7 synthetic CSVs (roster, components, monthly ops, agencies, spares and lead times, maintenance records, snags).
- **Roles:** commander / officer / viewer.
- Link: [github.com/SamruddhiMahajan1/predictive-aircraft-maintenance](https://github.com/SamruddhiMahajan1/predictive-aircraft-maintenance)

### 8.4 AeroSentinel: Harithdn/SIH249-Main
- **Workflow:** *Detect → Predict → Explain → Plan → Execute → Learn → Improve Readiness.*
- **Modules:** operations console; command (fleet overview, registry, alerts); aircraft workspace (health matrix, timeline, interactive schematic digital twin, telemetry, diagnostics); maintenance (predictions, anomalies, RUL, work orders); analytics (trends, failure analysis, scenario simulation); system (status, query console, audit).
- **Data:** SQLite auto-seeded with 24 aircraft × 7 components.
- **Work orders:** Detected → Approved → Scheduled → In Progress → Completed.
- **Responsible AI:** no autonomous authorisation; low-confidence flagging; demo labels.
- **Stack:** FastAPI, Vite/Node, SQLite/Postgres, Docker, pytest.
- Link: [github.com/Harithdn/SIH249-Main](https://github.com/Harithdn/SIH249-Main)

### 8.5 AirPower: qwertypoiuy9/SIH_249-devin
- **Pitch:** unify five siloed sources (onboard IoT/ACMS, technical records and logbooks, spares ERP, maintenance agencies/depots, flight ops) under one **ISO 13374 / OSA-CBM** analytics layer.
- **Pages:** fleet overview (readiness KPIs, downtime Pareto, data-source health, spares risk); inventory (20 airframes); **digital twin** (life-limited part usage: fatigue, engine hours, brake wear, tyres; 2 s telemetry); predictive fault detection (alerts, SHAP-style drivers, RUL with intervals, model metrics); maintenance planning (50 work orders, agency capacity, 14-day window); spares and stores (cover days, stockout/lead-time risk, **automatic indent from AI alerts**: RAISED → APPROVED → RECEIVED); data integration hub (feed health, quality guards, "bring your own sensor CSV"); analytics (before/after, MTBF/MTTR, **avoidable-downtime share**, model drift).
- **Algorithms:** EWMA baseline + z-score + **CUSUM** online detector; GBM-RUL; Isolation Forest; Autoencoder; **Weibull survival**; calibrated intervals; multi-echelon spares planning mentioned.
- **KPIs:** fleet availability %, MC %, **mean early-warning lead time**, **downtime-hours avoided**.
- **Integration targets:** ATA iSpec 2200; MIMOSA/OSA-CBM; MQTT/ARINC gateways; REST/GraphQL writes to AMOS/WinAir/Corridor.
- **Stack:** React + TS + Vite, hand-built SVG charts; localStorage persistence; Vercel demo; PPT, video script.
- Link: [github.com/qwertypoiuy9/SIH_249-devin](https://github.com/qwertypoiuy9/SIH_249-devin)

### 8.6 PS 26249 decision workspace: pallavpushkar3-gif/sih-project
- **Pitch:** a "local decision-workspace demonstrator" connecting labelled component records, maintenance constraints, inventory reservations and scenario availability simulation.
- **Tech:** React/TS/Vite + React Three Fiber (3D inspection); FastAPI/SQLAlchemy/Alembic/PostgreSQL with row locking; **OR-Tools CP-SAT planner**; **SimPy deterministic simulation**; Celery/RabbitMQ with outbox pattern; Playwright/Vitest/pytest.
- **Model:** frozen C-MAPSS FD001 model: MAE 8.72 cycles, RMSE 11.71, 98% interval coverage, mean width 58.2 cycles. Hash-verified artefacts.
- **Honesty statements:** "not an airworthiness, dispatch or operational-readiness system"; simulated projections, not observed improvements; no validated physical twin; the official test set has been inspected and cannot be reused as unseen evidence.
- Link: [github.com/pallavpushkar3-gif/sih-project](https://github.com/pallavpushkar3-gif/sih-project)

### 8.7 AeroNexus Fleet Intelligence: Team-404Does/gig
- Fleet command dashboard (readiness KPIs, risk queue, projected availability, health map); asset drill-down (30-cycle trends, **P10/P50/P90 RUL**, confidence, data lineage, feature attribution); maintenance planner (crew capacity, critical-spare disruption scenarios); **current vs AI-optimised availability comparison**; human approval workflow with audit.
- **APIs:** `/fleet/summary`, `/assets/{id}/health`, `/optimize/schedule`, `/plans/{id}/approve`, `/audit/events`.
- **Stack:** FastAPI, HTML/CSS/JS, Docker, Render.
- Link: [github.com/Team-404Does/gig](https://github.com/Team-404Does/gig)

### 8.8 READYFLEET: Saptarshi-Adhikari/readyfleet
- **Distinctive:** uses **live public data**: ADS-B operations (adsb.lol), weather (AWC/NOAA METAR), historical **FAA SDRS** maintenance, N-CMAPSS health; crew/spares synthetic; defence systems "not available". Strong **provenance tags** (source_id, ingestion_ts, synthetic flags) and **MC/PMC/NMC decision boundaries**.
- **Stack:** FastAPI with **SSE**, SQLite, scikit-learn, React/Vite; 35+ tests.
- Link: [github.com/Saptarshi-Adhikari/readyfleet](https://github.com/Saptarshi-Adhikari/readyfleet)

### 8.9 FleetAvail: Adi-Deshmukh/FleetAvail and dis-craft/FleetAvail
- **Pipeline:** telemetry + maintenance history → validation/features → anomaly + failure risk + RUL → **health fusion** (health score, RUL, failure probability, anomaly score, confidence, *data quality*) → digital twin (persistent JSON state) → maintenance/spares → fleet availability → dashboard.
- **Subsystems:** engine, hydraulics, electrical, landing gear. XGBoost (C-MAPSS) + Isolation Forest + temporal RUL; what-if degradation; constraint-aware planning with inventory allocation; WebSocket telemetry; cold-start fallbacks.
- **Disclaimer:** "software prototype, not a certified aviation or defence system".
- Links: [Adi-Deshmukh/FleetAvail](https://github.com/Adi-Deshmukh/FleetAvail), [dis-craft/FleetAvail](https://github.com/dis-craft/FleetAvail)

### 8.10 Related: Project GARUD (VIKASHL25/SIH-26), DRDO PS-26054 (UAV piston-engine health)
- Physics-informed digital twin for the **Rotax 914 engine on TAPAS-BH-201 (Rustom-II)**. CAN-FD telemetry from Simulink; five microservices; PCA anomaly detection (ROC-AUC 0.994); XGBoost degradation, fault classification (6 classes) and RUL with P10–P90; TreeSHAP; **federated-learning PoC** across UAVs; MongoDB with in-memory failover.
- Link: [github.com/VIKASHL25/SIH-26](https://github.com/VIKASHL25/SIH-26)

### 8.11 Pattern analysis: what (almost) every SIH team builds

| Feature | AERO-READY | PREDIX | Fleet DT | AeroSentinel | AirPower | Decision WS | AeroNexus | READYFLEET | FleetAvail |
|---|---|---|---|---|---|---|---|---|---|
| C-MAPSS / N-CMAPSS RUL | ✅ | ✅ | ✅ | ~ | ~ | ✅ | ~ | ✅ | ✅ |
| Anomaly detection (IF/AE) | ✅ | ✅ | — | ✅ | ✅ | — | — | — | ✅ |
| Health index / risk bands | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3D / schematic digital twin | ~ | — | ✅ | ✅ | ✅ | ✅ | — | — | ~ |
| SHAP explanations | ✅ | — | ✅ | — | ✅ | ✅ | ✅ | — | — |
| Spares stock check / Poisson | ✅ | ~ | ✅ | ✅ | ✅ | ✅ | ✅ | ~ | ✅ |
| MILP/CP-SAT scheduling | ✅ | — | — | — | ~ | ✅ | ✅ | — | ✅ |
| What-if simulation | ✅ | — | ~ | ✅ | ~ | ✅ | ✅ | — | ✅ |
| RAG/LLM copilot | ✅ | planned | — | — | — | — | — | — | — |
| Human approval + audit log | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ~ |
| Records-based reliability (Weibull) | — | — | ~ | — | ✅ | — | — | — | — |
| Repair-agency quality / rogue units | — | — | — | — | — | — | — | — | — |
| Geopolitical supply risk | — | — | — | — | — | — | — | — | — |
| Indigenisation prioritisation | — | — | — | — | — | — | — | — | — |
| Cross-service federated learning | — | — | — | — | — | — | — | — | — |
| Life-extension / retirement evidence | — | — | — | — | — | — | — | — | — |
| Surge / war sortie capacity | — | — | — | — | — | — | — | — | — |
| Data-quality → decision authority | — | — | ~ | ~ | ~ | — | ~ | ✅ (provenance) | ✅ (DQ in fusion) |
| Tamper-evident (cryptographic) ledger | — | — | — | — | — | ~ (hash artefacts) | — | — | — |
| Readiness value in squadron-equivalents | — | — | — | — | — | — | — | — | — |

(✅ present · ~ partial/mentioned · — absent, based on public READMEs at time of research)

**Reading the table.** The SIH field has converged on a **"C-MAPSS RUL + health dashboard + spares check + scheduler + 3D twin + SHAP"** template. Several teams show strong engineering (tests, offline-first, honest disclaimers). **None** addresses repair-agency quality, geopolitical supply risk, readiness-weighted indigenisation, cross-service learning, life extension, surge capacity, or a common readiness currency. These are the dimensions that matter most for India (Document 1).

---

## 9. Standards, specifications and frameworks

| Standard / framework | Scope | Relevance to NIRANTAR |
|---|---|---|
| **MSG-3** (A4A) | Logic for deriving scheduled maintenance tasks (on-condition, hard time, etc.) | Maps task types; mixes with Russian hard-time philosophy |
| **RCM**: SAE JA1011/JA1012, **MIL-STD-3034A** | Reliability-centred maintenance process | Framework for converting analytics into maintenance-programme changes |
| **DoDI 4151.22** (CBM+) | US DoD CBM+ policy | Reference policy model for India |
| **ISO 13374** / **MIMOSA OSA-CBM** | Condition-monitoring data-processing architecture (data acquisition → manipulation → state detection → health assessment → prognostics → advisory) | Reference architecture for analytics layering |
| **ISO 55000** | Asset management | Organisational framing of "Total Asset Reliability" |
| **ASD/AIA S-Series**: **S1000D** (technical publications), **S2000M** (materiel management), **S3000L** (logistics support analysis), **S4000P** (preventive maintenance development and continuous improvement), **S5000F** (in-service data feedback), **SX000i** (integration) | ILS data exchange | **S5000F** is the standard for exactly the "feedback from operation" that NIRANTAR consumes; S4000P governs updating maintenance programmes from that feedback ([S5000F](https://www.s-series.org/s5000f/)) |
| **ATA iSpec 2200 / ATA chapters** | Technical data and fault coding | Common coding for snags across origins |
| **MIL-STD-1530** (ASIP) | Structural integrity, individual aircraft tracking | Basis for usage-based lifing / life extension |
| **MIL-HDBK-516** | Airworthiness certification criteria | Reference for evidence standards |
| **DRDO ETAI** | Trustworthy AI evaluation (5 principles) | Mandatory alignment for Indian defence AI |
| **EASA AI Roadmap** (Level 1 assistance → Level 2 human-AI teaming → Level 3 autonomy) | Civil aviation AI assurance concepts | Useful framing of graduated autonomy (NIRANTAR stays at Level 1/2) |
| **CEMILAC/DGAQA procedures** | Indian military airworthiness and QA | Acceptance path for analytics-driven changes |
| **DPM 2025 / DAP 2020** | Indian procurement | Procurement path (iDEX → Make-II → system of record) |

---

## 10. Comparative capability matrix

Legend: ● strong · ◐ partial · ○ absent/unknown (public information only)

| Capability | PANDA / C3 | ERCM | ALIS/ODIN | NSS-A MOC | EXPRESS | RBS/OPUS10 | SIMLOX/TPS/LCOM | AFRL ADT | Skywise/SmartForce | AVIATAR | Ramco/IFS/Maximo | IIT-B Su-30 HI | SMS MiG-29K HUMS | SIH teams (typical) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sensor prognostics | ● | ○ | ◐ | ○ | ○ | ○ | ○ | ◐ | ● | ● | ◐ | ● | ● | ◐ (C-MAPSS) |
| Records-based reliability | ◐ | ● | ◐ | ◐ | ○ | ◐ | ◐ | ○ | ● | ● | ◐ | ○ | ○ | ○ |
| Spares demand from predictions | ● | ● | ◐ | ◐ | ○ | ○ | ○ | ○ | ◐ | ◐ | ◐ | ○ | ○ | ◐ |
| Readiness-based stock optimisation | ○ | ○ | ○ | ○ | ○ | ● | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Repair-queue prioritisation | ○ | ○ | ○ | ● | ● | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Availability simulation / forecast | ◐ | ○ | ○ | ◐ | ○ | ◐ | ● | ○ | ○ | ○ | ○ | ○ | ○ | ◐ |
| Per-tail structural lifing | ○ | ○ | ◐ | ○ | ○ | ○ | ○ | ● | ○ | ○ | ○ | ○ | ○ | ○ |
| Repair-agency effectiveness | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ◐ | ◐ | ◐ | ○ | ○ | ○ |
| Rogue-unit detection | ◐ | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ◐ | ● | ● | ○ | ○ | ○ |
| Geopolitical supply-risk modelling | ○ | ○ | ○ | ○ | ○ | ○ | ◐ (scenarios) | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Indigenisation prioritisation | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Cross-operator federated learning | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ◐ (shared platform) | ○ | ○ | ○ | ○ | ○ |
| Data-quality-gated decisions | ◐ | ○ | ○ (failed) | ◐ | ○ | ○ | ○ | ○ | ◐ | ◐ | ◐ | ○ | ○ | ◐ |
| Cryptographic audit trail | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Sovereign on-prem / air-gapped | ◐ | ● | ◐ | ● | ● | ● | ● | ● | ◐ | ○ | ◐ | ● | ● | ◐ |
| Multilingual voice capture | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Surge / wartime sortie modelling | ○ | ○ | ○ | ○ | ○ | ◐ (ASM) | ● (LCOM) | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Unified readiness currency across decisions | ○ | ○ | ○ | ◐ | ◐ | ◐ | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |

---

## 11. Lessons: what worked, what failed, and why

### 11.1 What worked
1. **Institutionalisation** (PANDA as system of record; NSS-A with SecDef mandate): technology plus governance plus mandate.
2. **Closing the loop to supply** (PANDA's supply-analyst role; C3 Readiness dynamic demand).
3. **Daily, data-driven prioritisation** (NSS-A Maintenance Operations Center; EXPRESS daily runs).
4. **Records-based reliability at scale** (ERCM: decades of data, two-year forecasts).
5. **Availability contracts with simulation** (BAE TPS; RAVEL; Rafale PBL).
6. **HUMS on helicopters** (US Army: fewer test flights, automated checks).
7. **In-house teams with domain proximity** (Royal Navy Motherlode by 1710 NAS).
8. **Explainability for maintainers** (Motherlode plain-language outputs; C3 evidence packages).

### 11.2 What failed or under-delivered
1. **ALIS:** bad data, heavy workload, contractor control, centralisation, no government data rights.
2. **Pilots that never scaled** (many DoD AI pilots; Indian iDEX/TDF point solutions).
3. **Prediction without logistics.** Alerts that cannot be acted on in time breed alarm fatigue.
4. **Sustaining gains.** NSS-A gains were hard to sustain once attention moved on. *Continuous* operating rhythms are needed, not campaigns.

### 11.3 Design principles extracted
- P1. **Optimise availability, not accuracy.**
- P2. **Data quality is a product feature,** visible and scored, and it gates decisions.
- P3. **Reduce, don't add, maintainer workload.**
- P4. **Human validation and accountability by design.**
- P5. **Government owns the data and models** (sovereignty; ALIS lesson).
- P6. **Daily operating rhythm** (a Maintenance Operations Center equivalent).
- P7. **Start with records** (most of India's fleets), add sensors where they exist.
- P8. **Couple prediction to provisioning and repair.**

---

## 12. Our initial draft ideas, re-checked against the landscape

Before this research we had a draft concept (see the problem brief). Here it is checked honestly against what exists:

| Draft idea | Already exists? | Evidence | Verdict for NIRANTAR |
|---|---|---|---|
| "Intelligence layer on top of e-MMS/IMMOLS, not a replacement" | Common best practice (PANDA on USAF systems; AirPower SIH team claims it) | §2.1, §8.5 | **Keep**, but it is a *principle*, not a novelty |
| "Weibull/survival on removal records for sensor-poor fleets" | **Yes**: USAF ERCM; airline reliability programmes; AirPower SIH team mentions Weibull | §2.2, §8.5 | **Keep and extend** (hierarchical Bayesian + environment + agency covariates); not novel alone |
| "Deep RUL only where sensors exist" | Standard good practice | §5.1 | Keep |
| "Rogue-unit detection from e-MMS + snags" | **Yes, in airline practice/products** (Ramco, AVIATAR, LAD paper, NAVAIR bad actors) | §4.7, §5.6 | **Keep but extend** to *repair-agency effectiveness* and routing, which is new for military multi-agency settings |
| "Close the loop to spares: 30/60/90-day demand vs stock and TAT" | **Yes**: PANDA, C3 Readiness, RBS/OPUS10, joint-optimisation papers; several SIH teams do simple versions | §2.1, §2.6, §4.1, §5.3 | **Keep but differentiate**: dynamic RBS driven by prognostics *plus* geopolitical lead-time risk *plus* a common readiness currency |
| "Bundle predicted tasks into planned inspections" | **Yes**: opportunistic maintenance literature; AirPower SIH team | §5.3, §8.5 | Keep as a module, not a novelty claim |
| "Evidence-backed recommendations; low-quality data lowers confidence; no auto-grounding" | **Partly**: C3 evidence packages; FleetAvail fuses data quality into health | §4.1, §8.9 | **Extend** into a formal *Evidence Grade → Action Authority* matrix (novel formalisation) |
| "Ed25519 hash-chained tamper-evident ledger" | Transparency logs exist (Rekor/Trillian); not seen in military maintenance-AI products | §7.9 | **Keep**: differentiator (decision accountability + part provenance) |
| "Fully offline, air-gapped on AFNet" | Many SIH teams are offline-first; SmartForce is geo-isolated | §4.2, §8.3 | Keep (mandatory, not novel) |
| "Discrete-event simulation of a 40-aircraft squadron under 3 policies" | **Yes**: LCOM, SIMLOX, BAE TPS, F-16 phase simulations; SIH Decision WS uses SimPy | §2.7, §4.9, §8.6 | **Keep as the demo**, but make the twin **national, multi-agency, continuously calibrated, and risk-aware** |

**Conclusion of the honesty check.** Many building blocks of the draft exist. NIRANTAR's novelty therefore cannot rest on any single block. It must come from a **new unifying idea** plus **several genuinely new modules** that matter specifically to India. Document 3 does exactly this.

---

## 13. White space: what nobody has built

Based on Sections 2–12, these gaps are **not addressed** by any solution we found (public information):

1. **A single readiness currency for every sustainment decision.** Each existing tool optimises its own proxy: backorders (RBS), repair priority (EXPRESS), alerts (PANDA), RMSE (SIH teams). **No system prices every candidate action (provision, expedite, repair-first, route, bundle, cannibalise, indigenise, extend life, sign contract) in the same unit of expected aircraft-available-days with uncertainty.**
2. **Readiness-at-Risk under geopolitical supply shocks.** No public tool reports tail-risk availability (e.g. "5th-percentile Su-30 availability over 180 days under a Russian-supply disruption") as a planning metric.
3. **Readiness-weighted indigenisation with a field-reliability feedback loop.** India has the world's largest active military spares-indigenisation programme, but no public model that ranks items by *availability gained per rupee under supply risk*, or tracks how indigenised parts actually perform.
4. **Repair-agency effectiveness intelligence.** Measuring the *quality* (not just turnaround) of each repair agency (BRD, HAL division, OEM, MSME) from post-repair survival, and routing work accordingly.
5. **Cross-service, privacy-preserving reliability commons** for common platforms (ALH, MiG-29/29K, Hawk, Do-228, Chetak/Cheetah, Mi-17), with **pharmacovigilance-style signal detection** for emerging fleet-wide hazards such as the 2025 ALH swashplate.
6. **Value-of-information-driven sensor retrofit and data-fix prioritisation.** Which sensor retrofits, or which data-quality fixes, buy the most availability?
7. **Evidence Grade → Action Authority governance**: formally linking data quality and model evidence to which decisions a recommendation may influence (ETAI-aligned).
8. **Life-extension and retirement-sequencing evidence engine** for a force that must stretch ageing fleets.
9. **Surge sortie-generation forecasting fused with live health and supply state**, for short, intense two-front conflicts.
10. **Voice-first, multilingual, offline capture** that improves data quality at the source.
11. **Cost-of-delay pricing** of administrative and contract decisions in squadron-days.
12. **A tamper-evident, citizen-auditor-grade (CAG-ready) chain of evidence** from sensor to decision.

These twelve gaps are the design brief for **NIRANTAR** (Document 3).

---

## 14. References

(Links appear inline throughout. Key consolidated list:)

**Military programmes**
- PANDA: https://defensescoop.com/2023/05/10/air-force-selects-ai-enabled-predictive-maintenance-program-as-system-of-record/ · https://www.aflcmc.af.mil/NEWS/Article/3381920/ · https://www.govconwire.com/articles/air-force-awards-450m-contract-to-c3-ai-for-predictive-analytics
- CBM+/ERCM: https://www.airandspaceforces.com/amc-planning-large-expansion-of-predictive-maintenance-effort · https://daytonaero.com/post/usaf-cbm-update-what-commercial-industry-oems-and-software-developers-need-to-know
- ALIS/ODIN: https://www.bloombergquint.com/business/f-35-s-17-billion-diagnostic-system-rife-with-flaws-gao-says · https://www.twz.com/31861/ · https://defensedaily.com/start-of-f-35-odin-software-fielding-to-squadrons-delayed-until-2025/air-force · https://gao.gov/blog/f-35-alis-looking-glass
- NSS-A: https://news.usni.org/2019/09/25/navy-surpasses-80-aircraft-readiness-goal-reaches-stretch-goal-of-341-up-fighters
- EXPRESS: https://static.e-publishing.af.mil/production/1/af_sustainment_ctr/publication/afsci23-103/afsci23-103.pdf
- RBS/METRIC/ASM: https://apps.dtic.mil/sti/pdfs/ADA207015.pdf · https://www.navy.mil/Press-Office/News-Stories/display-news/Article/2856341/
- LCOM: https://www.rand.org/pubs/research_memoranda/RM5544.html
- AFRL ADT: https://apps.dtic.mil/sti/pdfs/AD1062259.pdf
- BAE/Lanner Typhoon: https://lanner.com/insights/news/predictive-simulation-guides-fighter-jet-maintenance-for-raf.html
- DE&S Typhoon AI: https://des.mod.uk/what-we-do/defence-experts-case-studies/delivering-change-to-drive-excellence
- Royal Navy Motherlode: https://www.eplaneai.com/news/royal-navy-extends-ai-predictive-maintenance-to-fixed-wing-aircraft
- RAVEL: https://www.journal-aviation.com/en/news/43378-ravel-reconfigures-the-french-rafale-operational-condition-maintenance-ocm
- GAO-23-106217: https://www.gao.gov/products/gao-23-106217
- BCG 2026: https://www.bcg.com/publications/2026/how-to-improve-defense-aviation-mission-readiness

**Commercial**
- C3 AI Readiness: https://c3.ai/products/c3-ai-readiness-product/
- Airbus SmartForce: https://www.airbus.com/en/newsroom/press-releases/2018-07-airbus-launches-smartforce-services-bringing-the-power-of-data-to
- Boeing ROC: https://boeing.mediaroom.com/Boeing-Readiness-Operations-Center-Launches-to-Improve-Performance-for-Global-Defense-Operations
- AVIATAR: https://www.aviationtoday.com/2016/10/19/lufthansa-launches-predictive-maintenance-platform/
- IFS Maintenix for Defense: https://www.ifs.com/it/assets/2022/02/22/ifs-maintenix-for-defense
- Ramco: https://www.ramco.com/products/aviation-software/defense-industry · https://www.ramco.com/blog/monitoring-rogue-aircraft-component-reliability
- Systecon: https://dair.nps.edu/bitstream/123456789/4914/1/SYM-AM-23-147.pdf
- Odysight.ai: https://www.globenewswire.com/de/news-release/2024/03/11/2843783/0/en/

**Academic and data**
- C-MAPSS/N-CMAPSS: https://mdpi.com/2306-5729/6/1/5 · https://data.phmsociety.org/wp-content/uploads/sites/9/2021/08/2021_Data_Challenge.pdf
- NGAFID-MC: https://arxiv.org/abs/2210.07317v1 · https://ojs.aaai.org/index.php/AAAI/article/view/21538
- MaintNet: https://arxiv.org/pdf/2005.12443
- FAA SDRS: https://www.faa.gov/av-info/download_SDR
- DASHlink: https://c3.ndc.nasa.gov/dashlink/projects/85
- HUMS2023: https://humsconference.com.au/HUMS2023datachallenge/
- Airbus accelerometer: https://research-collection.ethz.ch/handle/20.500.11850/415151
- Conformal RUL: https://arxiv.org/pdf/2212.14612
- Federated RUL: https://arxiv.org/abs/2506.00499
- Rogue components (LAD): https://link.springer.com/article/10.1007/s10845-009-0351-1
- GRP/Kijima: https://en.wikipedia.org/wiki/Generalized_renewal_process
- Pharmacovigilance DA: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8193489/
- S5000F: https://www.s-series.org/s5000f/

**Open source**
- ProgPy: https://www.github.com/nasa/progpy
- reliability: https://pypi.org/project/reliability/
- xmetric: https://github.com/jto888/xmetric
- rul_codes_open: https://github.com/biswajitsahoo1111/rul_codes_open
- Predictive-Maintenance-using-LSTM: https://github.com/umbertogriffo/Predictive-Maintenance-using-LSTM
- IndicConformer: https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicconformer.html

**SIH 2026 SIH26249 repos**
- https://github.com/satyaganesh35/aero-ready
- https://github.com/ans-data-codes/predix-aircraft-predictive-maintenance
- https://github.com/SamruddhiMahajan1/predictive-aircraft-maintenance
- https://github.com/Harithdn/SIH249-Main
- https://github.com/qwertypoiuy9/SIH_249-devin
- https://github.com/pallavpushkar3-gif/sih-project
- https://github.com/Team-404Does/gig
- https://github.com/Saptarshi-Adhikari/readyfleet
- https://github.com/Adi-Deshmukh/FleetAvail · https://github.com/dis-craft/FleetAvail
- (related, PS-26054) https://github.com/VIKASHL25/SIH-26

---
*End of Document 2. Continue to `03_NIRANTAR_PROPOSED_SOLUTION.md`.*
