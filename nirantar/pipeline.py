"""End-to-end NIRANTAR Milestone-1 pipeline on BHARAT-FLEET synthetic data.

    history (status quo) -> SATYA checks -> DHANVANTARI Tier C fit
    -> SUSHRUTA scorecards and rogues -> DRISHTI signals
    -> SANJAYA four-policy experiment (normal + supply shock, RaR)
    -> CHANAKYA priced opportunities + Cost-of-Delay -> VISHWAKARMA ranking
    -> every artefact hashed and signed into the CHITRAGUPTA ledger
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from nirantar.bharat_fleet.world import World, make_world
from nirantar.chanakya.mrv import (Pricer, consumption_portfolio, greedy_portfolio, screen_and_price,
                                   surrogate_provision_values)
from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.dhanvantari.tier_c import TierCModel, fit_tier_c
from nirantar.drishti.signals import disproportionality, exposure_rates
from nirantar.records import to_frames
from nirantar.sanjaya.ensemble import P0, P1, P2, P3, run_ensemble, summarise
from nirantar.sanjaya.twin import SUPPLY_SHOCK, Scenario, Twin
from nirantar.satya.quality import check_spells, clean, dq_scores, evidence_grade
from nirantar.sushruta.agency import agency_scorecards, flag_rogues, serial_frailty
from nirantar.vishwakarma.rank import rank_indigenisation


@dataclass
class Config:
    world_seed: int = 7
    history_days: int = 1825
    history_seed: int = 99
    horizon_days: int = 365
    n_seeds: int = 20
    mrv_seeds: int = 16
    budget_lakh: float = 600.0
    top_k: int = 8
    out_dir: str = "experiments/results"
    quick: bool = False

    def quickened(self) -> "Config":
        return dataclasses.replace(self, n_seeds=6, mrv_seeds=4, top_k=4, history_days=1095)


@dataclass
class Outputs:
    report: dict = field(default_factory=dict)
    markdown: str = ""


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def run(cfg: Config = Config(), log=print) -> Outputs:
    if cfg.quick:
        cfg = cfg.quickened()
    t0 = time.time()
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "ledger.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = Ledger(ledger_path)
    node = Signer.generate("NIRANTAR-national-node")
    steward = Signer.generate("data-steward-B1")
    officer = Signer.generate("CEngO-B1")

    world = make_world(seed=cfg.world_seed)
    family_of = {p: v.family for p, v in world.pns.items()}

    # 1. history under the status quo -> records
    log(f"[1/8] Simulating {cfg.history_days} days of status-quo history ...")
    hist = Twin(world, P0, cfg.history_days, seed=cfg.history_seed, record=True).run()
    fr = to_frames(hist.records)
    ledger.append("data_batch", {"source": "BHARAT-FLEET history", "spells": len(fr["spells"]),
                                 "repairs": len(fr["repairs"]), "snags": len(fr["snags"]),
                                 "sha256": _sha(hist.records["spells"][:2000])}, steward)

    # 2. SATYA
    log("[2/8] SATYA data-quality checks ...")
    issues = check_spells(fr["spells"], fr["repairs"], horizon_day=cfg.history_days)
    dq = dq_scores(fr["spells"], issues)
    spells = clean(fr["spells"], issues)
    ledger.append("dq_report", {"issues": issues["issue"].value_counts().to_dict(),
                                "min_dq": float(dq["dq"].min())}, steward)

    # 3. DHANVANTARI Tier C + SUSHRUTA
    log("[3/8] Fitting DHANVANTARI Tier C (hierarchical Weibull + Kijima + frailty) ...")
    dm: TierCModel = fit_tier_c(spells, family_of)
    frail = serial_frailty(dm, spells, family_of)
    dm.rogue_flags = flag_rogues(frail, p_min=0.5)
    scorecards = agency_scorecards(dm, fr["repairs"])
    ledger.append("model_version", {"model": "dhanvantari.tier_c", "params_sha256": _sha(dm.x.round(6).tolist()),
                                    "n_spells": dm.n_spells, "n_failures": dm.n_failures}, node)

    truth_q = {a: world.agencies[a].q for a in dm.agencies}
    tp = len(dm.rogue_flags & world.rogue_serials)
    rogue_eval = {"flagged": len(dm.rogue_flags), "true_positives": tp,
                  "precision": round(tp / max(len(dm.rogue_flags), 1), 2),
                  "recall": round(tp / max(len(world.rogue_serials), 1), 2)}

    # 4. DRISHTI
    log("[4/8] DRISHTI signal detection ...")
    sig = disproportionality(fr["snags"], exposure=exposure_rates(fr["spells"], family_of))
    planted = {(f, e, world.env_mode_boost[(f, e)]) for (f, e) in world.env_mode_boost}
    found_sig = {tuple(x) for x in sig[sig["signal"]][["family", "env", "mode"]].values} if len(sig) else set()
    found_cand = {tuple(x) for x in sig[sig["candidate"]][["family", "env", "mode"]].values} if len(sig) else set()

    # 5. provisioning portfolios (status quo vs CHANAKYA)
    log("[5/8] Building provisioning portfolios ...")
    start = hist.snapshot
    vals = surrogate_provision_values(world, start, dm, cfg.horizon_days)
    smart = tuple(greedy_portfolio(vals, cfg.budget_lakh, cfg.horizon_days))
    recent = fr["spells"][fr["spells"]["install_day"] > cfg.history_days - 365]
    cons = tuple(consumption_portfolio(world, recent, cfg.budget_lakh))

    # 6. four-policy experiment + ablation
    log("[6/8] Four-policy experiment (normal + supply shock) ...")
    seeds = list(range(1000, 1000 + cfg.n_seeds))
    arms = [
        (P0, cons), (P1, cons), (P2, cons),
        (dataclasses.replace(P2, name="P2 + smart routing", smart_routing=True, routing_mix=0.0), cons),
        (dataclasses.replace(P2, name="P2 + rogue quarantine", rogue_quarantine=True), cons),
        (dataclasses.replace(P2, name="P2 + MRV portfolio"), smart),
        (P3, smart),
    ]
    experiment = []
    base_waad = {}
    for scen in (Scenario(), SUPPLY_SHOCK):
        for pol, acts in arms:
            res = run_ensemble(world, pol, cfg.horizon_days, seeds, scen, acts, dm, start)
            s = summarise(res)
            waad = np.array([r.waad for r in res])
            if pol.name == P0.name:
                base_waad[scen.name] = waad
            d = waad - base_waad[scen.name]
            sqe = d.mean() / (18 * cfg.horizon_days)
            experiment.append({
                "scenario": scen.name, "policy": pol.name, "availability": round(s.mean, 4),
                "ci95": [round(s.ci95[0], 4), round(s.ci95[1], 4)], "RaR10": round(s.rar, 4),
                "CRaR10": round(s.crar, 4), "fighter": round(s.by_fleet["FighterH"], 4),
                "helo": round(s.by_fleet["HeloU"], 4), "nmcs_days": round(s.nmcs_days, 1),
                "preventive_swaps": round(s.preventive, 1),
                "delta_waad_vs_P0": round(float(d.mean()), 1),
                "delta_waad_ci95": [round(float(d.mean() - 1.96 * d.std(ddof=1) / np.sqrt(len(d))), 1),
                                    round(float(d.mean() + 1.96 * d.std(ddof=1) / np.sqrt(len(d))), 1)],
                "fighter_sqe_equivalent": round(float(sqe), 3),
                "spend_lakh": round(s.spend_lakh, 1),
            })
            log(f"      {scen.name:13s} {pol.name:28s} A={s.mean:.3f} CRaR10={s.crar:.3f}")

    # 7. CHANAKYA priced opportunities + cost of delay
    log("[7/8] Pricing opportunities (paired simulation) ...")
    mseeds = list(range(2000, 2000 + cfg.mrv_seeds))
    pricer = Pricer(world, P3, cfg.horizon_days, mseeds, start, dm, Scenario(), base_actions=())
    opps = screen_and_price(pricer, vals, top_k=cfg.top_k, horizon=cfg.horizon_days)
    opp_rows = []
    for r in opps:
        ev = evidence_grade(float(dq.set_index("pn")["dq"].get(r.action.pn, 1.0)),
                            dm.n_failures_by_pn.get(r.action.pn, 0))
        row = r.as_dict()
        row["evidence_grade"] = ev.grade
        row["authority"] = "Logistics officer" if ev.grade in ("E1", "E2") else "Logistics + CEngO"
        rec = ledger.append("recommendation", row, node)
        decision = "accept" if (r.ci95[0] > 0 and ev.grade in ("E1", "E2", "E3")) else "defer"
        ledger.append("decision", {"recommendation_seq": rec["seq"], "verdict": decision,
                                   "reason_code": "MRV_CI_POSITIVE" if decision == "accept" else "UNCERTAIN"}, officer)
        opp_rows.append(row)
    cod = None
    if opps:
        per_day, now, later = pricer.cost_of_delay(opps[0].action, delay_days=60.0)
        cod = {"action": opps[0].action.label(), "mrv_now": round(now.mean_aad, 1),
               "mrv_if_delayed_60d": round(later.mean_aad, 1), "cost_of_delay_waad_per_day": round(per_day, 3)}

    log("[8/8] VISHWAKARMA indigenisation ranking ...")
    indig = rank_indigenisation(world, start, P3, dm, cfg.horizon_days, mseeds)

    sth = ledger.tree_head(node)
    report = {
        "config": dataclasses.asdict(cfg),
        "runtime_s": round(time.time() - t0, 1),
        "history": {"availability": {k: round(v, 4) for k, v in hist.mean_availability.items()},
                    "spells": len(fr["spells"]), "repairs": len(fr["repairs"]), "snags": len(fr["snags"])},
        "satya": {"issues": issues["issue"].value_counts().to_dict(), "min_dq": float(dq["dq"].min())},
        "dhanvantari": {
            "agency_q": {a: {"estimate": [round(v, 3) for v in dm.q_interval(a)], "truth": truth_q[a]}
                         for a in dm.agencies},
            "env_effects": {f"{f}|{e}": {"estimate": [round(v, 3) for v in dm.env_multiplier(f, e)],
                                         "truth_eta_multiplier": world.env_effect[(f, e)]}
                            for (f, e) in world.env_effect},
            "frailty_k": round(dm.frailty_k, 2),
        },
        "sushruta": {"scorecards": scorecards.to_dict("records"), "rogues": rogue_eval},
        "drishti": {"planted": sorted(map(list, planted)), "signals": sorted(map(list, found_sig)),
                    "candidates": sorted(map(list, found_cand)),
                    "planted_found_as_signal": len(found_sig & planted),
                    "planted_found_as_candidate": len(found_cand & planted),
                    "false_signals": len(found_sig - planted)},
        "portfolios": {"status_quo": [a.label() for a in cons], "chanakya": [a.label() for a in smart]},
        "experiment": experiment,
        "opportunities": opp_rows,
        "cost_of_delay": cod,
        "indigenisation": indig.to_dict("records"),
        "ledger": {"entries": len(ledger.entries), "tree_head": sth, "verify_all": ledger.verify_all(sth)},
    }
    (out_dir / "milestone1_report.json").write_text(json.dumps(report, indent=2, default=str))
    md = render_markdown(report)
    (out_dir / "milestone1_report.md").write_text(md)
    log(f"Done in {report['runtime_s']} s -> {out_dir}/milestone1_report.md")
    return Outputs(report, md)


def _table(rows: list[dict], cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)


def render_markdown(r: dict) -> str:
    exp = r["experiment"]
    md = ["# NIRANTAR Milestone 1: engine results on BHARAT-FLEET (synthetic)\n",
          "> All data is synthetic, generated by BHARAT-FLEET with known ground truth. "
          "Numbers demonstrate the methods; they are not IAF results.\n",
          f"Runtime: {r['runtime_s']} s. Seeds per arm: {r['config']['n_seeds']} "
          f"(quick mode: {r['config']['quick']}).\n",
          "## 1. Four-policy experiment (365 days, paired seeds)\n",
          _table(exp, ["scenario", "policy", "availability", "ci95", "CRaR10", "fighter", "helo",
                       "delta_waad_vs_P0", "delta_waad_ci95", "fighter_sqe_equivalent", "preventive_swaps"]),
          "\nCRaR10 = mean availability in the worst 10% of simulated futures (tail risk). "
          "delta_waad = change in role-weighted aircraft-available-days vs P0 on identical random streams.\n",
          "## 2. SATYA data quality\n", f"Issues on raw history: {r['satya']['issues']}; min DQ score {r['satya']['min_dq']}.\n",
          "## 3. DHANVANTARI / SUSHRUTA: recovering hidden truth\n",
          _table([{"agency": a, "q estimate [90% CI]": v["estimate"], "true q": v["truth"]}
                  for a, v in r["dhanvantari"]["agency_q"].items()], ["agency", "q estimate [90% CI]", "true q"]),
          "\nEnvironment effects (eta multiplier relative to the family's average environment; truth is the absolute multiplier):\n\n",
          _table([{"family|env": k, "estimate [90% CI]": v["estimate"], "true multiplier": v["truth_eta_multiplier"]}
                  for k, v in r["dhanvantari"]["env_effects"].items()], ["family|env", "estimate [90% CI]", "true multiplier"]),
          f"\nRogue detection: {r['sushruta']['rogues']}\n",
          "## 4. DRISHTI signals\n",
          f"Planted effects: {r['drishti']['planted']}\n\n"
          f"Confirmed signals: {r['drishti']['signals']} (false: {r['drishti']['false_signals']})\n\n"
          f"Planted effects surfaced as candidates: {r['drishti']['planted_found_as_candidate']}/{len(r['drishti']['planted'])}\n",
          "## 5. CHANAKYA priced opportunities (top screened, paired simulation)\n",
          _table(r["opportunities"], ["action", "mrv_aad", "ci95", "p_positive", "cost_lakh", "aad_per_crore",
                                      "evidence_grade", "authority", "explanation"]),
          f"\nCost of Delay: {r['cost_of_delay']}\n",
          "## 6. VISHWAKARMA indigenisation ranking\n",
          _table(r["indigenisation"], ["pn", "name", "origin", "cost_lakh", "mrv_normal", "mrv_shock",
                                       "delta_crar_shock_pts", "waad_per_crore"]),
          "## 7. CHITRAGUPTA ledger\n",
          f"{r['ledger']['entries']} signed entries; tree root `{r['ledger']['tree_head']['root'][:16]}...`; "
          f"failed verifications: {r['ledger']['verify_all']}\n"]
    return "\n".join(md)
