"""Back-test: plan from the records, score in the hidden truth.

The synthetic fleet lets us do what a real deployment never can: compare what
the records-only system believes and decides against what is actually true.
At each cut-off day:

1. Run the true fleet to the cut-off and export its records (e-MMS/IMMOLS style).
2. Import them into a fresh store and estimate the world and fleet state.
3. **State and parameters**: compare the estimate to the true snapshot and world.
4. **Forecast**: 90-day availability under today's procedures, simulated from
   the estimate vs from the truth (same random streams).
5. **Decisions**: build today's plan twice, once from the estimate (what a
   deployed NIRANTAR would recommend) and once from the true state and world
   (an oracle with perfect information), and score both in the true world on
   futures neither planner saw. The gap is the cost of planning from records:
   the regret.
"""
from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from nirantar.bharat_fleet.world import World
from nirantar.chanakya.desk import build_plan
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.records import to_frames
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Action, Twin
from nirantar.setu.estimate import Estimated, estimate
from nirantar.setu.export import export, serial_id
from nirantar.setu.ingest import Importer
from nirantar.setu.schema import Store


def _truth_id(e: Estimated, sid: int | None) -> int | None:
    """Planning id -> the simulator's serial id (through the recorded serial number)."""
    if sid is None:
        return None
    name = e.serial_of.get(int(sid))
    return int(name[3:]) if name else None


def to_truth(e: Estimated, a: Action) -> Action:
    return replace(a, serial=_truth_id(e, a.serial)) if a.serial is not None else a


def state_accuracy(e: Estimated, truth: dict) -> dict:
    sid = lambda i: e.id_of.get(serial_id(i))
    slots = [(t, tuple(k), v) for t, inst in truth["installed"].items() for k, v in inst.items()]
    inst_ok = sum(e.start["installed"].get(t, {}).get(k) == sid(v) for t, k, v in slots)
    t_stock = {(tuple(k), sid(s)) for k, v in truth["stock"].items() for s in v}
    e_stock = {(tuple(k), s) for k, v in e.start["stock"].items() for s in v}
    tp = {sid(p["sid"]): p for p in truth["pipeline"]}
    ep = {p["sid"]: p for p in e.start["pipeline"]}
    both = set(tp) & set(ep)
    tw = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in truth["waiting"]}
    ew = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in e.start["waiting"]}
    return {
        "fitted_units_correct": round(inst_ok / max(len(slots), 1), 4), "fitted_slots": len(slots),
        "shelf_units_correct": round(len(t_stock & e_stock) / max(len(t_stock | e_stock), 1), 4),
        "pipeline_units_found": round(len(both) / max(len(set(tp) | set(ep)), 1), 4),
        "pipeline_stage_correct": round(sum(tp[k]["type"] == ep[k]["type"] for k in both) / max(len(both), 1), 4),
        "pipeline_days_left_mae": round(float(np.mean([abs(tp[k]["dt"] - ep[k]["dt"]) for k in both])), 1)
        if both else None,
        "waiting_aircraft": [len(tw), len(ew)], "waiting_correct": round(len(set(tw) & set(ew)) / max(len(tw), 1), 4),
        "supply_regime": {"true": truth["regimes"], "estimated": e.start["regimes"]},
    }


def parameter_accuracy(e: Estimated, world: World) -> dict:
    st = e.agency_stats.set_index("agency")
    ag = {a.id: {"tat_true": a.tat_median_days, "tat_est": round(float(st.loc[a.id, "tat_median"]), 1),
                 "q_true": a.q, "q_est": round(float(e.world.agencies[a.id].q), 3),
                 "leg_true": a.transport_days, "leg_est": round(float(st.loc[a.id, "back_leg_base"]), 1),
                 "slots_true": a.servers, "slots_est": int(st.loc[a.id, "servers"])}
          for a in world.agencies.values() if a.id in st.index}
    eta_err = [abs(e.world.pns[p].eta / world.pns[p].eta - 1) for p in world.pns if p in e.world.pns]
    beta_err = [abs(e.world.pns[p].beta / world.pns[p].beta - 1) for p in world.pns if p in e.world.pns]
    return {"agencies": ag, "eta_median_rel_error": round(float(np.median(eta_err)), 3),
            "beta_median_rel_error": round(float(np.median(beta_err)), 3)}


def _paired(world, start, actions, seeds, horizon, dm) -> np.ndarray:
    base = [Twin(world, P0, horizon, seed=s, start=start, resume=True, decision_model=dm).run() for s in seeds]
    plan = [Twin(world, P0, horizon, seed=s, start=start, resume=True, decision_model=dm, actions=actions).run()
            for s in seeds]
    return np.array([p.waad - b.waad for p, b in zip(plan, base)])


def _ci(x: np.ndarray) -> list[float]:
    h = 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0
    return [round(float(x.mean() - h), 1), round(float(x.mean() + h), 1)]


def backtest_cutoff(world: World, cutoff: int, history_seed: int = 99, horizon: int = 90, plan_seeds: int = 24,
                    score_seeds: int = 32, workers: int | None = None, log=print) -> dict:
    t0 = time.time()
    hist = Twin(world, P0, cutoff, seed=history_seed, record=True).run()
    truth = hist.snapshot
    family_of = {p: v.family for p, v in world.pns.items()}
    with tempfile.TemporaryDirectory() as tmp:
        export(world, hist.records, truth, cutoff, Path(tmp) / "x")
        st = Store(Path(tmp) / "s.db")
        Importer(st).import_folder(Path(tmp) / "x")
        e = estimate(st)
        st.close()
    log(f"  day {cutoff}: records imported and estimated ({time.time() - t0:.0f} s)")
    out = {"cutoff_day": cutoff, "history_seed": history_seed, "state": state_accuracy(e, truth), "parameters": parameter_accuracy(e, world),
           "notes": e.notes}

    # forecast: availability under today's procedures, from the estimate vs from the truth
    fseeds = range(9100, 9100 + score_seeds)
    f_true = [Twin(world, P0, horizon, seed=s, start=truth, resume=True).run().overall_availability for s in fseeds]
    f_est = [Twin(e.world, P0, horizon, seed=s, start=e.start, resume=True).run().overall_availability
             for s in fseeds]
    out["forecast"] = {"horizon_days": horizon, "availability_true": round(float(np.mean(f_true)), 4),
                       "availability_estimated": round(float(np.mean(f_est)), 4),
                       "error_points": round(100 * (float(np.mean(f_est)) - float(np.mean(f_true))), 2)}

    # decisions: plan from records vs oracle plan, both scored in the truth on unseen futures
    dm_true = fit_tier_c(to_frames(hist.records)["spells"], family_of)
    n_fail = dict(e.model.n_failures_by_pn)
    kw = dict(horizon=horizon, n_seeds=plan_seeds, n_screen=min(8, plan_seeds), workers=workers)
    p_est = build_plan(e.world, e.start, e.model, P0, n_fail, e.dq, **kw)
    p_orc = build_plan(world, truth, dm_true, P0, dict(dm_true.n_failures_by_pn), e.dq, **kw)
    # perfect state and world, but only what the records tell about today's supply regime:
    # separates what records lose from what nobody could know yet
    blind = {**truth, "regimes": e.start["regimes"], "regime_probs": e.start["regime_probs"]}
    p_bld = build_plan(world, blind, dm_true, P0, dict(dm_true.n_failures_by_pn), e.dq, **kw)
    log(f"  day {cutoff}: plans built ({time.time() - t0:.0f} s)")
    from nirantar.chanakya.desk import action_from_item
    a_est = tuple(to_truth(e, action_from_item(it)) for it in p_est["items"])
    a_orc = tuple(action_from_item(it) for it in p_orc["items"])
    a_bld = tuple(action_from_item(it) for it in p_bld["items"])
    sseeds = range(20_000, 20_000 + score_seeds)          # futures neither planner priced
    v_est = _paired(world, truth, a_est, sseeds, horizon, dm_true) if a_est else np.zeros(score_seeds)
    v_orc = _paired(world, truth, a_orc, sseeds, horizon, dm_true) if a_orc else np.zeros(score_seeds)
    v_bld = _paired(world, truth, a_bld, sseeds, horizon, dm_true) if a_bld else np.zeros(score_seeds)
    reg = v_orc - v_est
    claimed = (p_est["joint"] or {}).get("mrv", 0.0)
    out["decisions"] = {
        "records_plan": {"actions": len(a_est), "cost_lakh": p_est["cost_lakh"], "claimed_wAAD": claimed,
                         "claimed_ci95": (p_est["joint"] or {}).get("ci95"),
                         "realised_wAAD": round(float(v_est.mean()), 1), "realised_ci95": _ci(v_est),
                         "kinds": _kinds(p_est)},
        "oracle_plan": {"actions": len(a_orc), "cost_lakh": p_orc["cost_lakh"],
                        "claimed_wAAD": (p_orc["joint"] or {}).get("mrv", 0.0),
                        "realised_wAAD": round(float(v_orc.mean()), 1), "realised_ci95": _ci(v_orc),
                        "kinds": _kinds(p_orc)},
        "oracle_regime_as_records": {"actions": len(a_bld), "realised_wAAD": round(float(v_bld.mean()), 1),
                                     "realised_ci95": _ci(v_bld)},
        "regret_wAAD": round(float(reg.mean()), 1), "regret_ci95": _ci(reg),
        "regret_from_records_wAAD": round(float((v_bld - v_est).mean()), 1),
        "regret_from_records_ci95": _ci(v_bld - v_est),
        "share_of_oracle_value": round(float(v_est.mean() / v_orc.mean()), 3) if v_orc.mean() > 0 else None,
        "score_futures": score_seeds,
    }
    out["runtime_s"] = round(time.time() - t0, 1)
    return out


def _kinds(plan: dict) -> dict[str, int]:
    k: dict[str, int] = {}
    for it in plan["items"]:
        k[it["kind"]] = k.get(it["kind"], 0) + 1
    return k


CASES = ((1095, 99), (1460, 99), (1825, 99), (1500, 7), (1825, 5))     # (cut-off day, history seed)


def backtest(world: World, cases=CASES, log=print, **kw) -> dict:
    rows = [backtest_cutoff(world, c, history_seed=s, log=log, **kw) for c, s in cases]
    d = [r["decisions"] for r in rows]
    return {
        "cutoffs": rows,
        "summary": {
            "forecast_error_points": [r["forecast"]["error_points"] for r in rows],
            "records_plan_realised": [x["records_plan"]["realised_wAAD"] for x in d],
            "records_plan_claimed": [x["records_plan"]["claimed_wAAD"] for x in d],
            "oracle_plan_realised": [x["oracle_plan"]["realised_wAAD"] for x in d],
            "oracle_regime_as_records_realised": [x["oracle_regime_as_records"]["realised_wAAD"] for x in d],
            "regret": [x["regret_wAAD"] for x in d],
            "regret_from_records": [x["regret_from_records_wAAD"] for x in d],
            "share_of_oracle_value": [x["share_of_oracle_value"] for x in d],
            "mean_regret": round(float(np.mean([x["regret_wAAD"] for x in d])), 1),
            "mean_regret_from_records": round(float(np.mean([x["regret_from_records_wAAD"] for x in d])), 1),
            "mean_overclaim": round(float(np.mean([x["records_plan"]["claimed_wAAD"] - x["records_plan"]["realised_wAAD"]
                                                   for x in d])), 1),
            "mean_forecast_error_points": round(float(np.mean([r["forecast"]["error_points"] for r in rows])), 2),
        },
    }
