"""VISHWAKARMA: readiness-weighted indigenisation ranking.

For every foreign-sourced part number, price the action "qualify an Indian
repair/supply source" on the twin under normal operations *and* under a supply
shock, then rank by risk-weighted readiness gained per crore.
"""
from __future__ import annotations

import pandas as pd

from nirantar.bharat_fleet.world import World
from nirantar.chanakya.mrv import Pricer
from nirantar.sanjaya.twin import INDIGENOUS_AGENCY, Action, DecisionModel, Policy, SUPPLY_SHOCK, Scenario


def rank_indigenisation(world: World, start: dict, policy: Policy, dm: DecisionModel, horizon: int,
                        seeds, base_actions: tuple[Action, ...] = (), qualify_days: float = 90.0,
                        dev_cost_factor: float = 30.0, shock_weight: float = 0.5,
                        shock: Scenario = SUPPLY_SHOCK) -> pd.DataFrame:
    normal = Pricer(world, policy, horizon, seeds, start, dm, Scenario(), base_actions)
    stressed = Pricer(world, policy, horizon, seeds, start, dm, shock, base_actions)
    rows = []
    for pn, p in world.pns.items():
        if p.origin == "IN":
            continue
        a = Action("indigenise", pn, agency=INDIGENOUS_AGENCY.id, start_day=qualify_days,
                   cost_lakh=dev_cost_factor * p.unit_cost_lakh)
        n, s = normal.price(a), stressed.price(a)
        risk_weighted = (1 - shock_weight) * n.mean_aad + shock_weight * s.mean_aad
        rows.append({
            "pn": pn, "name": p.name, "origin": p.origin, "cost_lakh": a.cost_lakh,
            "mrv_normal": round(n.mean_aad, 1), "ci_normal": [round(v, 1) for v in n.ci95],
            "mrv_shock": round(s.mean_aad, 1), "ci_shock": [round(v, 1) for v in s.ci95],
            "delta_crar_shock_pts": round(s.delta_crar_pts, 2),
            "risk_weighted_mrv": round(risk_weighted, 1),
            "waad_per_crore": round(risk_weighted / (a.cost_lakh / 100.0), 1),
        })
    df = pd.DataFrame(rows)
    return df.sort_values("waad_per_crore", ascending=False).reset_index(drop=True)
