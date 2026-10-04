"""CHANAKYA: Marginal Readiness Value (MRV), portfolios and Cost-of-Delay.

MRV of an action = expected change in weighted aircraft-available-days (wAAD:
each type's days weighted by its role value) over a horizon, estimated by *paired* simulation: the twin is run with and without
the action on identical random streams (common random numbers), so the
difference isolates the action's effect with low variance.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import poisson, t as student_t

from nirantar.bharat_fleet.world import World
from nirantar.sanjaya.ensemble import rar
from nirantar.sanjaya.twin import Action, DecisionModel, Policy, RunResult, Scenario, Twin


@dataclass
class MRVResult:
    action: Action
    mean_aad: float               # weighted aircraft-available-days (wAAD)
    ci95: tuple[float, float]
    p_positive: float
    delta_crar_pts: float
    sqe: float
    cost_lakh: float
    explanation: str
    per_seed: list[float] = field(default_factory=list)

    @property
    def aad_per_crore(self) -> float:
        return self.mean_aad / (self.cost_lakh / 100.0) if self.cost_lakh > 0 else float("inf")

    def as_dict(self) -> dict:
        return {"action": self.action.label(), "kind": self.action.kind, "pn": self.action.pn,
                "base": self.action.base, "qty": self.action.qty,
                "mrv_aad": round(self.mean_aad, 1), "ci95": [round(self.ci95[0], 1), round(self.ci95[1], 1)],
                "p_positive": round(self.p_positive, 2), "delta_crar_pts": round(self.delta_crar_pts, 2),
                "sqe": round(self.sqe, 4), "cost_lakh": self.cost_lakh,
                "aad_per_crore": None if math.isinf(self.aad_per_crore) else round(self.aad_per_crore, 1),
                "explanation": self.explanation}


class Pricer:
    """Prices actions against a fixed baseline using paired simulations."""

    def __init__(self, world: World, policy: Policy, horizon: int, seeds, start: dict | None = None,
                 dm: DecisionModel | None = None, scenario: Scenario = Scenario(),
                 base_actions: tuple[Action, ...] = (), alpha: float = 0.1):
        self.w, self.policy, self.H, self.seeds = world, policy, horizon, list(seeds)
        self.start, self.dm, self.scenario, self.base_actions, self.alpha = start, dm, scenario, base_actions, alpha
        self.baseline: list[RunResult] = [self._run(s, base_actions) for s in self.seeds]

    def _run(self, seed: int, actions: tuple[Action, ...]) -> RunResult:
        return Twin(self.w, self.policy, self.H, seed=seed, scenario=self.scenario, actions=actions,
                    decision_model=self.dm, start=self.start).run()

    def price(self, action: Action) -> MRVResult:
        runs = [self._run(s, self.base_actions + (action,)) for s in self.seeds]
        diffs = np.array([a.waad - b.waad for a, b in zip(runs, self.baseline)])
        n = len(diffs)
        mean = float(diffs.mean())
        if n > 1:
            half = float(student_t.ppf(0.975, n - 1) * diffs.std(ddof=1) / math.sqrt(n))
        else:
            half = float("nan")
        base_av = [r.overall_availability for r in self.baseline]
        act_av = [r.overall_availability for r in runs]
        d_crar = 100.0 * (rar(act_av, self.alpha)[1] - rar(base_av, self.alpha)[1])
        ft = self.w.fleets[self.w.pns[action.pn].fleet]
        return MRVResult(action, mean, (mean - half, mean + half), float((diffs > 0).mean()), d_crar,
                         sqe=mean / (ft.role_weight * ft.squadron_ue * self.H), cost_lakh=action.cost_lakh,
                         explanation=trace_diff(self.baseline, runs), per_seed=diffs.tolist())

    def cost_of_delay(self, action: Action, delay_days: float = 30.0) -> tuple[float, MRVResult, MRVResult]:
        """Readiness lost per day of delaying ``action`` (AAD/day)."""
        now = self.price(action)
        later = self.price(Action(**{**action.__dict__, "start_day": action.start_day + delay_days}))
        return (now.mean_aad - later.mean_aad) / delay_days, now, later


def trace_diff(base: list[RunResult], act: list[RunResult], top: int = 3) -> str:
    """Counterfactual explanation: which tails' waiting-for-parts time the action removes."""
    gain: dict[str, float] = defaultdict(float)
    for b, a in zip(base, act):
        for tail in set(b.nmcs_by_tail) | set(a.nmcs_by_tail):
            gain[tail] += (b.nmcs_by_tail.get(tail, 0.0) - a.nmcs_by_tail.get(tail, 0.0)) / len(base)
    total = sum(gain.values())
    best = sorted(((v, k) for k, v in gain.items() if v > 0.05), reverse=True)[:top]
    if total <= 0.05 or not best:
        return "No material change in waiting-for-parts (NMCS) time."
    names = ", ".join(f"{k} ({v:.1f} d)" for v, k in best)
    return f"Cuts waiting-for-parts time by {total:.1f} aircraft-days on average; largest on {names}."


# ---------------------------------------------------------------- provisioning portfolio


def _planning_ages(world: World, start: dict, dm: DecisionModel) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """(base, pn) -> [(env, estimated effective age)] for installed serials."""
    out: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    tails = {t["id"]: t for t in world.tails}
    for tail_id, inst in start["installed"].items():
        base = tails[tail_id]["base"]
        env = world.base_env(base)
        for slot, sid in inst.items():
            pn = slot[0]
            v = 0.0
            for g, x, kind in start["hist"].get(sid, []):
                v = 0.0 if kind == "OH" else v + dm.q_hat.get(g, 0.3) * x
            out[(base, pn)].append((env, v + float(start["X"][sid])))
    return out


def _hazard(dm: DecisionModel, pn: str, env: str, age: float, dh: float = 1.0) -> float:
    return dm.cum_hazard(pn, env, age, age + dh) / dh


def _expected_multiplier(world: World, country: str, days: float = 365.0, start_state: int = 0) -> float:
    """Mean supply-regime multiplier over the next ``days`` given today's regime."""
    m = world.regimes[country]
    if len(m.states) == 1:
        return 1.0
    P = np.array(m.transition)
    dist = np.zeros(len(m.states))
    dist[start_state] = 1.0
    mult = np.array(m.tat_multiplier)
    total = 0.0
    n = max(int(days), 1)
    for _ in range(n):
        total += float(dist @ mult)
        dist = dist @ P
    return total / n


def surrogate_provision_values(world: World, start: dict, dm: DecisionModel, horizon: int,
                               routing: dict[str, str] | None = None) -> dict[tuple[str, str], dict]:
    """Fast analytic screening (Palm's theorem): pipeline mean and spare level per (base, pn)."""
    ages = _planning_ages(world, start, dm)
    stock = defaultdict(int)
    for key, sids in start["stock"].items():
        stock[tuple(key)] += len(sids)
    for item in start["pipeline"]:
        base = item.get("from") or item.get("base")
        stock[(base, item["pn"])] += 1
    # inventory position = on hand + in pipeline - backorders (aircraft already waiting)
    tails = {t["id"]: t for t in world.tails}
    for tail_id, inst in start["installed"].items():
        t = tails[tail_id]
        for pn, p in world.pns.items():
            if p.fleet != t["fleet"]:
                continue
            missing = p.positions - sum(1 for slot in inst if slot[0] == pn)
            stock[(t["base"], pn)] -= missing
    out = {}
    for (base, pn), lst in ages.items():
        p = world.pns[pn]
        rate = world.fleets[p.fleet].fh_per_day
        demand = sum(_hazard(dm, pn, env, a) for env, a in lst) * rate          # removals/day
        g = (routing or {}).get(pn, p.default_agency)
        ag = world.agencies[g]
        pipe_days = ag.tat_median_days + 2 * ag.transport_days * _expected_multiplier(world, ag.country, horizon)
        out[(base, pn)] = {"mu": demand * pipe_days, "s": stock[(base, pn)], "demand_per_day": demand,
                           "weight": world.fleets[p.fleet].role_weight,
                           "lead": p.procurement_days * _expected_multiplier(world, p.origin, 1.0),
                           "unit_cost": p.unit_cost_lakh}
    return out


def greedy_portfolio(values: dict, budget_lakh: float, horizon: int) -> list[Action]:
    """Marginal allocation: next unit to the (base, pn) with the largest expected
    backorder reduction x usable days per rupee."""
    s = {k: v["s"] for k, v in values.items()}
    bought = defaultdict(int)
    left = budget_lakh
    while True:
        best, best_ratio = None, 0.0
        for k, v in values.items():
            if v["unit_cost"] > left:
                continue
            gain = float(poisson.sf(max(s[k], -1), v["mu"])) if s[k] >= 0 else 1.0   # EBO(s) - EBO(s+1)
            usable = max(horizon - v["lead"], 0.0)
            ratio = v.get("weight", 1.0) * gain * usable / v["unit_cost"]
            if ratio > best_ratio:
                best, best_ratio = k, ratio
        if best is None:
            break
        bought[best] += 1
        s[best] += 1
        left -= values[best]["unit_cost"]
    return [Action("provision", pn, base, qty=q, cost_lakh=q * values[(base, pn)]["unit_cost"])
            for (base, pn), q in sorted(bought.items())]


def consumption_portfolio(world: World, spells, budget_lakh: float) -> list[Action]:
    """Status-quo allocation: buy in proportion to last period's removals (ignores cost and pipeline)."""
    fails = spells[spells["removal_reason"] == "failure"].groupby(["base", "pn"]).size()
    bought = defaultdict(int)
    left = budget_lakh
    while True:
        best, best_score = None, 0.0
        for (base, pn), c in fails.items():
            cost = world.pns[pn].unit_cost_lakh
            if cost > left:
                continue
            score = c / (bought[(base, pn)] + 1)
            if score > best_score:
                best, best_score = (base, pn), score
        if best is None:
            break
        bought[best] += 1
        left -= world.pns[best[1]].unit_cost_lakh
    return [Action("provision", pn, base, qty=q, cost_lakh=q * world.pns[pn].unit_cost_lakh)
            for (base, pn), q in sorted(bought.items())]


def screen_and_price(pricer: Pricer, values: dict, top_k: int = 8, horizon: int = 365) -> list[MRVResult]:
    """Screen single-unit provisioning candidates analytically, then price the top-K by simulation."""
    cands = []
    for (base, pn), v in values.items():
        p_short = float(poisson.sf(v["s"], v["mu"])) if v["s"] >= 0 else 1.0
        gain = v.get("weight", 1.0) * p_short * max(horizon - v["lead"], 0.0)
        cands.append((gain / v["unit_cost"], base, pn, v["unit_cost"]))
    cands.sort(reverse=True)
    results = [pricer.price(Action("provision", pn, base, 1, cost_lakh=c)) for _, base, pn, c in cands[:top_k]]
    return sorted(results, key=lambda r: r.aad_per_crore, reverse=True)
