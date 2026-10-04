"""Ensemble forecasting and Readiness-at-Risk on the sustainment twin."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nirantar.bharat_fleet.world import World
from nirantar.sanjaya.twin import Action, DecisionModel, Policy, RunResult, Scenario, Twin

P0 = Policy("P0 Reactive", routing_mix=0.3)
P1 = Policy("P1 Prediction-only", predictive_swap=True, routing_mix=0.3)
P2 = Policy("P2 Predict+Spares+Schedule", predictive_swap=True, lateral_transfer=True,
            need_based_return=True, aog_priority=True, routing_mix=0.3)
P3 = Policy("P3 NIRANTAR", predictive_swap=True, lateral_transfer=True, need_based_return=True,
            aog_priority=True, smart_routing=True, rogue_quarantine=True)
POLICIES = (P0, P1, P2, P3)


def run_ensemble(world: World, policy: Policy, horizon: int, seeds, scenario: Scenario = Scenario(),
                 actions: tuple[Action, ...] = (), dm: DecisionModel | None = None,
                 start: dict | None = None) -> list[RunResult]:
    return [Twin(world, policy, horizon, seed=s, scenario=scenario, actions=actions,
                 decision_model=dm, start=start).run() for s in seeds]


def rar(values, alpha: float = 0.1) -> tuple[float, float]:
    """Readiness-at-Risk (alpha-quantile) and conditional RaR (mean of the worst alpha share)."""
    v = np.sort(np.asarray(values, dtype=float))
    q = float(np.quantile(v, alpha))
    tail = v[v <= q + 1e-12]
    return q, float(tail.mean()) if len(tail) else q


@dataclass
class EnsembleSummary:
    policy: str
    scenario: str
    n: int
    mean: float
    ci95: tuple[float, float]
    rar: float
    crar: float
    by_fleet: dict[str, float]
    nmcs_days: float
    failures: float
    preventive: float
    spend_lakh: float


def summarise(results: list[RunResult], alpha: float = 0.1) -> EnsembleSummary:
    av = np.array([r.overall_availability for r in results])
    se = av.std(ddof=1) / np.sqrt(len(av)) if len(av) > 1 else 0.0
    r_, c_ = rar(av, alpha)
    fleets = results[0].mean_availability.keys()
    return EnsembleSummary(
        policy=results[0].policy, scenario=results[0].scenario, n=len(results),
        mean=float(av.mean()), ci95=(float(av.mean() - 1.96 * se), float(av.mean() + 1.96 * se)),
        rar=r_, crar=c_,
        by_fleet={f: float(np.mean([r.mean_availability[f] for r in results])) for f in fleets},
        nmcs_days=float(np.mean([r.nmcs_days for r in results])),
        failures=float(np.mean([r.failures for r in results])),
        preventive=float(np.mean([r.preventive_swaps for r in results])),
        spend_lakh=float(np.mean([r.spend_lakh for r in results])),
    )


def fan_chart(results: list[RunResult], fleet: str | None = None,
              quantiles=(0.1, 0.5, 0.9)) -> dict[float, np.ndarray]:
    """Daily availability quantiles across the ensemble (whole force or one fleet)."""
    if fleet is None:
        w = {f: None for f in results[0].fleet_daily_availability}
        series = []
        for r in results:
            tot = sum(r.fleet_daily_availability[f] * 1.0 for f in w)
            series.append(tot / len(w))
        arr = np.array(series)
    else:
        arr = np.array([r.fleet_daily_availability[fleet] for r in results])
    return {q: np.quantile(arr, q, axis=0) for q in quantiles}
