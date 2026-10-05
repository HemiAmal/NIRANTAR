# NIRANTAR: 7-minute demo script

> Built into the console as **Guided demo** (top-right button). This page is the same script for rehearsal and as a printed fallback.
>
> Everything shown is synthetic data (BHARAT-FLEET). Say so once, at the start.

The storyline follows [Document 3 §13.3](03_NIRANTAR_PROPOSED_SOLUTION.md#133-demo-storyline-7-minutes-72-hours-at-air-force-station-nirantar), adjusted to what is built.

---

## Before you present

1. Start the console: `python -m nirantar serve`, then open http://127.0.0.1:8050 in **Chrome or Edge** (needed for the microphone).
2. Press **Guided demo**, then on the *Preparation* card press **Reset the station to day 0**. This clears the operations clock and keeps today's plan.
3. Set the browser zoom so the four tiles fit on one row. Choose light or dark with **Theme**.
4. Rehearse once with **Do it** on every step. A full run takes about a minute of machine time. The two re-planning steps take about 15 seconds each, so talk through them.

Keys while the guide is open: **→** next, **←** back, **D** do it. **Minimise** shrinks the guide to its buttons so it does not cover the screen.

---

## The script

| Slot | Step | Press | Say (numbers on the day are filled in live by the guide) |
|---|---|---|---|
| 0:00–0:45 | **The problem in one chart** (Readiness room) | Show the 12-month forecast | With today's procedures the force keeps about **66%** of its aircraft available, against a 75% goal. The band is the spread over 20 simulated futures: readiness is a risk, not a number. Most of the gap is aircraft *waiting for parts*. |
| 0:45–1:45 | **Morning huddle** (Decision desk) | Open the plan's top action | **33 of 70** aircraft are waiting for parts. The desk priced **95** possible actions and proposes **20** for **₹28 lakh**, worth **+188** weighted aircraft-days over 90 days (CI 165–211). Each names its approver and the cost of a week's delay. "What the simulation shows" lists which aircraft stop waiting. |
| 1:45–2:30 | **SAARTHI** | Speak (example) and sign | A technician says the snag in Hindi. Each field shows *heard* or *inferred*; nothing is invented. Checks run against the records, then the entry is signed. *(With a microphone: press the mic and say "एफ आई बी वन जीरो सेवन, दूसरा हाइड्रोलिक पंप लीक, बदल दिया".)* |
| 2:30–3:15 | **DRISHTI** (Fleet signals) | Show the signal table | Hydraulics corrosion in humid north-east bases, **2.6×** the fleet rate per flight hour, found from records alone, the way drug-safety teams find side effects. Action: a targeted inspection for that context only. |
| 3:15–3:45 | **Approve and run a week** (Decision desk) | Approve the plan, advance 7 days | Each approver signs only what the Action Authority Matrix allows. The clock applies the approved actions; a **shadow fleet** meets the same failures with no decisions. The gap between the lines is measured, not estimated. |
| 3:45–4:30 | **Shock** | Declare a 120-day disruption | Russian shipping, customs and payments disrupted for 120 days, signed into the ledger. The desk re-plans: **15** actions worth **+316**, led by **re-routing engine fuel pump repairs to BRD-1** (a ~262-day loop becomes ~38 days). The card states the trade-off: those repairs are less durable. |
| 4:30–5:00 | **SUSHRUTA** (Repair agencies) | Show agency quality | Repair quality per agency, estimated from records alone with an interval, checked against the hidden truth. Rogue units flagged with **88%** precision. That is where the routing trade-off comes from. |
| 5:00–5:45 | **The proof** (Readiness room, supply shock) | Show the policy comparison | Under a supply shock NIRANTAR keeps **70.5%** available vs **62.0%**: **+1,996** weighted aircraft-days, about **0.30** fighter squadrons. Prediction alone *hurts* (−565). The value is in pricing and routing. On the clock: the decisions' gain over the shadow fleet so far. |
| 5:45–6:30 | **Trust** (Data & ledger) | Verify, then tamper | Every snag, recommendation, decision, execution and scenario is signed and hash-chained. The tamper demo edits a copy and verification catches it; the real ledger is intact. Evidence grade decides who may approve. NIRANTAR never grounds or releases an aircraft. |
| 6:30–7:00 | **Close** | none | **"NIRANTAR doesn't predict failures. It prices readiness, continuously."** Ask: a shadow-mode pilot on two bases and one BRD with real records. Everything shown runs offline on one laptop. |

---

## If something goes wrong

| Problem | Do this |
|---|---|
| Microphone blocked or no network for speech | Use the example button (the guide's **Do it** already does). Structuring, checks and signing run offline. |
| A re-plan is slow | Keep talking; the guide's button shows "Working…" and the desk shows progress. On a 4-core laptop it is about 15 s. |
| A judge wants to try SAARTHI | Let them type any snag in Hinglish; ambiguous ones ("B1 05 pump leaking") show SAARTHI asking instead of guessing. |
| Running long | Skip SUSHRUTA (step 7); the routing card already makes its point. |
| Want to start over | Guide → Back to *Preparation* → **Reset the station to day 0**. |

## Likely questions

[Document 3 §19.2](03_NIRANTAR_PROPOSED_SOLUTION.md#192-judge-qa-prepared-answers) has prepared answers. Have these numbers ready:

- **Fresh-future check.** Today's plan is worth +188 on the futures used to choose it, and **+162** on fresh ones. The console always shows the fresh check.
- **SAARTHI accuracy.** 32 of 36 hand-written utterances fully right on the first run, and zero silent errors after review. Not yet tested on real flight-line speech.
- **What is not modelled.** Repair queues never form in the synthetic world, the model is not refitted day by day, and routing is all-or-nothing per part (docs 07 and 08 list the limits).
