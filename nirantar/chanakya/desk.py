"""CHANAKYA decision desk: today's board, candidate actions, a priced plan, approvals.

From the current fleet state (the end of the record) the desk

1. builds the **board**: every aircraft's status, the parts it is waiting for,
   when the repair pipeline is expected to return one, and its 7-day risk of a
   new failure (DHANVANTARI);
2. generates **candidate actions** for the people who can act today:
   controlled cannibalisation (CEngO), lateral transfer, expedite, purchase
   (logistics), repair-queue priority (BRD Chief Engineer);
3. **prices** each by paired simulation (MRV, common random numbers) against
   today's procedures;
4. selects a **plan** under budget and resource conflicts (one spare cannot be
   sent twice, one donor cannot give twice), verifies the plan jointly, and
   prices waiting (Cost-of-Delay);
5. attaches the **evidence grade** and the **approving authority** from the
   Action Authority Matrix (Document 3, section 10.2).

NIRANTAR proposes; people decide. Nothing here grounds or releases an aircraft:
a cannibalisation donor must already be unserviceable.
"""
from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import t as student_t

from nirantar.bharat_fleet.world import World
from nirantar.chanakya.mrv import surrogate_provision_values, trace_diff
from nirantar.sanjaya.twin import (EXPEDITE_LEG_DAYS, EXPEDITE_TAT_FACTOR, LATERAL_DAYS, Action, DecisionModel,
                                   Policy, Scenario, Twin)
from nirantar.sanjaya.views import fleet_view
from nirantar.satya.quality import evidence_grade

TRANSFER_COST_LAKH = 0.5
CANN_COST_LAKH = 0.3
STATUS = {0: "MC", 1: "NMCM", 2: "NMCS"}
AUTHORITY = {
    "transfer": ("Logistics officer", "Logistics officer", "Logistics officer + CEngO"),
    "expedite": ("Logistics officer", "Logistics officer", "Logistics officer + CEngO"),
    "provision": ("Logistics officer", "Logistics officer", "Logistics officer + CEngO"),
    "priority": ("BRD Chief Engineer", "BRD Chief Engineer", "HQMC review"),
    "cann": ("CEngO", "CEngO", "CEngO + Command"),
    "route": ("HQMC review", "HQMC review", "HQMC review"),
}
KIND_LABEL = {"cann": "Controlled cannibalisation", "transfer": "Lateral transfer", "expedite": "Expedite",
              "priority": "Repair-queue priority", "provision": "Purchase", "route": "Repair routing"}


def _lc(name: str) -> str:
    """'Hydraulic pump' -> 'hydraulic pump', but keep acronyms: 'AC generator', 'ECS cooling turbine'."""
    return name if len(name) > 1 and name[1].isupper() else name[:1].lower() + name[1:]


def _waited(days: float) -> str:
    return "has just started waiting" if days < 1 else f"has waited {days:.0f} d"


def expedite_cost(world: World, pn: str) -> float:
    return round(1.0 + 0.05 * world.pns[pn].unit_cost_lakh, 2)


# ---------------------------------------------------------------- board


def _est_age(start: dict, dm: DecisionModel, sid: int) -> float:
    v = 0.0
    for g, x, kind in start["hist"].get(sid, []):
        v = 0.0 if kind == "OH" else v + dm.q_hat.get(g, 0.3) * x
    return v + float(start["X"][sid])


def _mult(world: World, start: dict, country: str, scenario: Scenario | None = None) -> float:
    """Today's supply-regime multiplier for a supplier country (a declared disruption overrides)."""
    m = world.regimes.get(country)
    if m is None or len(m.states) == 1:
        return 1.0
    idx = int(start.get("regimes", {}).get(country, 0))
    for c, state, s0, s1 in (scenario.forced if scenario else ()):
        if c == country and s0 <= 0 < s1:
            idx = m.states.index(state)
    return m.tat_multiplier[idx]


def _leg_days(world: World, agency: str, start: dict, scenario: Scenario | None = None) -> float:
    ag = world.agencies.get(agency)
    if ag is None:
        return 3.0
    return ag.transport_days * _mult(world, start, ag.country, scenario)


def _express_days(world: World, agency: str | None, start: dict, scenario: Scenario | None = None) -> float:
    ag = world.agencies.get(agency) if agency else None
    return EXPEDITE_LEG_DAYS * (_mult(world, start, ag.country, scenario) if ag else 1.0)


def pipeline_etas(world: World, start: dict, scenario: Scenario | None = None) -> dict[tuple[str, str], list[dict]]:
    """(base, pn) -> pipeline units heading there, with an expected arrival day."""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for it in start["pipeline"]:
        base = it.get("base") or it.get("from")
        pn = it["pn"]
        if it["type"] == "arrive":
            eta, where = it["dt"], "in transit to base"
        elif it["type"] == "inrepair":
            eta, where = it["dt"] + _leg_days(world, it["agency"], start, scenario), f"in repair at {it['agency']}"
        else:
            ag = world.agencies.get(it["agency"])
            tat = ag.tat_median_days if ag else 30.0
            eta = it["dt"] + tat + _leg_days(world, it["agency"], start, scenario)
            where = f"queued at {it['agency']}" if it["dt"] <= 0 else f"in transit to {it['agency']}"
        last = (start["hist"].get(it["sid"]) or [[None]])[-1][0]
        out[(base, pn)].append({"sid": int(it["sid"]), "eta": float(eta), "where": where, "type": it["type"],
                                "agency": it.get("agency") or last, "dt": float(it["dt"])})
    for v in out.values():
        v.sort(key=lambda d: d["eta"])
    return out


def board(world: World, start: dict, dm: DecisionModel, risk_days: int = 7, scenario: Scenario | None = None) -> dict:
    etas = pipeline_etas(world, start, scenario)
    holes = defaultdict(list)                     # (base, pn) -> waiting entries, longest wait first
    for w in start.get("waiting", []):
        base = next(t["base"] for t in world.tails if t["id"] == w["tail"])
        holes[(base, w["pn"])].append(dict(w, days=float(w["days"])))
    for k in holes:
        holes[k].sort(key=lambda d: -d["days"])
        for i, h in enumerate(holes[k]):          # FIFO: the i-th waiter gets the i-th arriving unit
            arr = etas.get(k, [])
            h["eta"] = round(arr[i]["eta"], 1) if i < len(arr) else None
            h["eta_source"] = arr[i]["where"] if i < len(arr) else "no unit in the repair pipeline"
    tails = []
    for t in world.tails:
        inst = start["installed"].get(t["id"], {})
        env = world.base_env(t["base"])
        rate = world.fleets[t["fleet"]].fh_per_day
        surv, worst = 1.0, (0.0, None)
        for (pn, _k), sid in inst.items():
            p = float(dm.fail_prob(pn, env, _est_age(start, dm, sid), risk_days * rate))
            surv *= 1.0 - p
            if p > worst[0]:
                worst = (p, pn)
        waiting = [dict(h, name=world.pns[pn].name) for (b, pn), hs in holes.items() if b == t["base"]
                   for h in hs if h["tail"] == t["id"]]
        work = float(start.get("work_left", {}).get(t["id"], 0.0))
        status = "NMCS" if waiting else ("NMCM" if work > 1e-9 else "MC")
        tails.append({"id": t["id"], "base": t["base"], "fleet": t["fleet"], "status": status,
                      "waiting": waiting, "work_left": round(work, 1),
                      "risk7": round(1.0 - surv, 3), "risk_pn": worst[1],
                      "risk_part": world.pns[worst[1]].name if worst[1] else None})
    stock = {f"{b}|{pn}": len(v) for (b, pn), v in ((tuple(k), v) for k, v in start["stock"].items()) if v}
    return {"tails": tails, "stock": stock, "holes": {f"{b}|{pn}": v for (b, pn), v in holes.items()},
            "risk_days": risk_days}


# ---------------------------------------------------------------- candidates


@dataclass
class Candidate:
    action: Action
    text: str
    reason: str
    uses: tuple = ()                               # exclusive resources: ("stock", base, pn), ("donor", tail), ...
    fixes: tuple = ()                              # ("hole", base, pn) slots this action can fill
    priced: dict = field(default_factory=dict)


def _tail_base(world: World) -> dict[str, str]:
    return {t["id"]: t["base"] for t in world.tails}


def candidates(world: World, start: dict, dm: DecisionModel, brd: dict, horizon: int,
               scenario: Scenario | None = None) -> list[Candidate]:
    etas = pipeline_etas(world, start, scenario)
    stock = defaultdict(int)
    for k, v in start["stock"].items():
        stock[tuple(k)] += len(v)
    tails = {t["id"]: t for t in world.tails}
    by_tail = {t["id"]: t for t in brd["tails"]}
    out: list[Candidate] = []
    seen = set()

    def add(c: Candidate):
        key = c.action
        if key not in seen:
            seen.add(key)
            out.append(c)

    for key, hs in brd["holes"].items():
        base, pn = key.split("|")
        p = world.pns[pn]
        name = _lc(p.name)
        for h in hs:
            eta = h["eta"]
            wait_txt = f"expected back in ~{eta:.0f} d" if eta is not None else "no unit in the repair pipeline"
            if eta is not None and eta <= LATERAL_DAYS + 1:
                continue                                       # a unit arrives anyway
            # controlled cannibalisation: donor is down for another part and will stay down longer
            donors = []
            for d in brd["tails"]:
                if d["id"] == h["tail"] or d["base"] != base or d["fleet"] != p.fleet or d["status"] != "NMCS":
                    continue
                if any(x["pn"] == pn for x in d["waiting"]):
                    continue
                if not any(slot[0] == pn for slot in start["installed"].get(d["id"], {})):
                    continue
                d_eta = max((x["eta"] if x["eta"] is not None else math.inf) for x in d["waiting"])
                r_eta = eta if eta is not None else math.inf
                if d_eta < r_eta and not math.isinf(r_eta):
                    continue                                   # donor would be back first: consolidating on it gains little
                donors.append((d_eta, d))
            for d_eta, d in sorted(donors, key=lambda x: -x[0])[:2]:      # the longest-waiting donors
                why = ", ".join(_lc(x["name"]) for x in d["waiting"])
                d_txt = "no unit in the pipeline" if math.isinf(d_eta) else f"~{d_eta:.0f} d"
                add(Candidate(
                    Action("cann", pn, base=base, src=d["id"], tail=h["tail"], cost_lakh=CANN_COST_LAKH),
                    f"Move the {name} from {d['id']} to {h['tail']}",
                    f"{h['tail']} {_waited(h['days'])} for it ({wait_txt}); {d['id']} is already down "
                    f"for {why} ({d_txt}), so one aircraft flies instead of none.",
                    uses=(("tail", d["id"]), ("tail", h["tail"])), fixes=(("hole", base, pn),)))
            # lateral transfer from a base with a spare on the shelf
            for other in world.fleets[p.fleet].tails_per_base:
                if other != base and stock[(other, pn)] > 0:
                    add(Candidate(
                        Action("transfer", pn, base=base, src=other, qty=1, cost_lakh=TRANSFER_COST_LAKH),
                        f"Send 1 {name} from {other} stores to {base}",
                        f"{base} has {len(hs)} aircraft waiting for it ({wait_txt} for the first); "
                        f"{other} holds {stock[(other, pn)]} on the shelf. Arrives in {LATERAL_DAYS:.0f} d.",
                        uses=(("stock", other, pn),), fixes=(("hole", base, pn),)))
            # purchase, only if it can arrive inside the horizon
            lead = p.procurement_days * (world.regimes[p.origin].tat_multiplier[start.get("regimes", {}).get(p.origin, 0)]
                                         if p.origin in world.regimes else 1.0)
            if lead < horizon * 0.6:
                add(Candidate(
                    Action("provision", pn, base=base, qty=1, cost_lakh=p.unit_cost_lakh),
                    f"Buy 1 {name} for {base}",
                    f"{len(hs)} aircraft waiting at {base}; typical lead time ~{lead:.0f} d.",
                    fixes=(("hole", base, pn),)))
        # expedite units already heading here (no more than the aircraft waiting, plus one)
        def express(it):
            return _express_days(world, it["agency"], start, scenario)
        useful = [it for it in etas.get((base, pn), [])
                  if not (it["eta"] <= express(it) + 2 or it["type"] == "arrive" and it["dt"] <= express(it))]
        for it in useful[:len(hs) + 1]:
            fast = (min(it["dt"], express(it)) if it["type"] == "arrive" else
                    it["dt"] * EXPEDITE_TAT_FACTOR + express(it) if it["type"] == "inrepair" else None)
            fast_txt = f"~{fast:.0f} d instead of ~{it['eta']:.0f} d" if fast is not None else \
                f"jumps the queue and flies back (normally ~{it['eta']:.0f} d)"
            add(Candidate(
                Action("expedite", pn, base=base, serial=it["sid"], agency=it["agency"],
                       cost_lakh=expedite_cost(world, pn)),
                f"Expedite S/N {world.sn(it['sid'])} ({name}) for {base}",
                f"Unit is {it['where']}; with overtime and air freight it reaches {base} in {fast_txt}"
                f"{' (customs and payment delays still apply)' if express(it) > EXPEDITE_LEG_DAYS else ''}. "
                f"{len(hs)} aircraft waiting there.",
                uses=(("serial", it["sid"]),), fixes=(("hole", base, pn),)))
            if it["type"] == "job" and it["dt"] <= 0:
                add(Candidate(
                    Action("priority", pn, base=base, serial=it["sid"], agency=it["agency"]),
                    f"Repair S/N {world.sn(it['sid'])} ({name}) first at {it['agency']}",
                    f"It sits in {it['agency']}'s queue while {len(hs)} aircraft at {base} wait for this part.",
                    uses=(("serial", it["sid"]),), fixes=(("hole", base, pn),)))

    # crisis routing: send future repairs of a part away from a supplier whose shipping is stressed or disrupted
    for pn, p in world.pns.items():
        dflt = world.agencies[p.default_agency]
        m_d = _mult(world, start, dflt.country, scenario)
        if m_d <= 1.0:
            continue
        old_days = dflt.tat_median_days + 2 * dflt.transport_days * m_d
        for g in p.eligible_agencies:
            ag = world.agencies[g]
            if g == p.default_agency or _mult(world, start, ag.country, scenario) > 1.0:
                continue
            new_days = ag.tat_median_days + 2 * ag.transport_days
            q_note = (f" Trade-off: {g} repairs are less durable (estimated q {dm.q_hat.get(g, ag.q):.2f} vs "
                      f"{dm.q_hat.get(dflt.id, dflt.q):.2f}), so revert when supply normalises."
                      if dm.q_hat.get(g, ag.q) > dm.q_hat.get(dflt.id, dflt.q) + 0.05 else "")
            add(Candidate(
                Action("route", pn, agency=g),
                f"Send future {_lc(p.name)} repairs to {g} instead of {dflt.id}",
                f"{dflt.id} shipping is {'disrupted' if m_d >= 8 else 'stressed'} ({m_d:.0f}x slower): a repair loop takes "
                f"~{old_days:.0f} d there vs ~{new_days:.0f} d at {g}.{q_note}",
                uses=(("route", pn),)))

    # proactive transfers: a base with no spare and likely demand soon, another base with two or more
    vals = surrogate_provision_values(world, start, dm, horizon)
    for (base, pn), v in vals.items():
        if stock[(base, pn)] > 0 or f"{base}|{pn}" in brd["holes"]:
            continue
        p30 = 1.0 - math.exp(-v["demand_per_day"] * 30.0)
        if p30 < 0.5:
            continue
        for other in world.fleets[world.pns[pn].fleet].tails_per_base:
            if other != base and stock[(other, pn)] >= 2:
                add(Candidate(
                    Action("transfer", pn, base=base, src=other, qty=1, cost_lakh=TRANSFER_COST_LAKH),
                    f"Pre-position 1 {_lc(world.pns[pn].name)} from {other} to {base}",
                    f"{base} has none on the shelf and a {p30:.0%} chance of needing one in 30 days; "
                    f"{other} holds {stock[(other, pn)]}.",
                    uses=(("stock", other, pn),)))
    return out


# ---------------------------------------------------------------- pricing and plan

_CTX: dict = {}


def _init_worker(ctx: dict) -> None:
    _CTX.clear()
    _CTX.update(ctx)


def _run_job(job: tuple) -> tuple:
    """One twin run in a worker: (actions, seed) on the whole fleet, or (view, actions, seed) on a sub-fleet."""
    view, actions, seed = job if len(job) == 3 else (None, *job)
    c = _CTX
    if view is None:
        world, start = c["world"], c["start"]
    else:                                   # (fleet, bases or None): built once per worker, then reused
        cache = c.setdefault("_views", {})
        if view not in cache:
            cache[view] = fleet_view(c["world"], c["start"], [view[0]], view[1])
        world, start = cache[view]
    r = Twin(world, c["policy"], c["horizon"], seed=seed, actions=actions, decision_model=c["dm"],
             start=start, resume=True, scenario=c["scenario"]).run()
    return r.waad, r.overall_availability, r.nmcs_days, dict(r.nmcs_by_tail)


@dataclass
class _Res:
    waad: float
    overall_availability: float
    nmcs_days: float
    nmcs_by_tail: dict


class Runner:
    """Runs batches of (actions, seed) on a process pool (or serially with workers=1)."""

    def __init__(self, world, policy, horizon, start, dm, workers: int | None = None, scenario: Scenario = Scenario()):
        self.ctx = {"world": world, "policy": policy, "horizon": horizon, "start": start, "dm": dm,
                    "scenario": scenario}
        self.workers = workers if workers is not None else max(1, min(os.cpu_count() or 1, 8))
        self.ex = None
        if self.workers > 1:
            try:
                self.ex = ProcessPoolExecutor(self.workers, initializer=_init_worker, initargs=(self.ctx,))
            except (OSError, NotImplementedError):
                self.ex = None

    def run(self, jobs: list[tuple]) -> list[_Res]:
        if self.ex is not None:
            try:
                out = list(self.ex.map(_run_job, jobs, chunksize=max(1, len(jobs) // (4 * self.workers))))
                return [_Res(*o) for o in out]
            except Exception:           # broken pool (e.g. blocked process start): fall back to serial
                self.close()
        _init_worker(self.ctx)
        return [_Res(*_run_job(j)) for j in jobs]

    def close(self) -> None:
        if self.ex is not None:
            self.ex.shutdown(cancel_futures=True)
            self.ex = None


def _grade(pn: str, n_fail: dict[str, int], dq: dict[str, float]):
    return evidence_grade(dq.get(pn, 1.0), n_fail.get(pn, 0))


def _ci(diffs: np.ndarray) -> tuple[float, float, float]:
    n = len(diffs)
    m = float(diffs.mean())
    h = float(student_t.ppf(0.975, n - 1) * diffs.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    return m, m - h, m + h


def _price(base: list[_Res], runs: list[_Res]) -> dict:
    diffs = np.array([a.waad - b.waad for a, b in zip(runs, base)])
    m, lo, hi = _ci(diffs)
    return {"mrv": round(m, 1), "ci95": [round(lo, 1), round(hi, 1)],
            "p_positive": round(float((diffs > 0).mean()), 2), "explanation": trace_diff(base, runs),
            "futures": len(diffs)}


def build_plan(world: World, start: dict, dm: DecisionModel, policy: Policy, n_fail: dict[str, int],
               dq: dict[str, float], horizon: int = 90, n_seeds: int = 24, n_screen: int = 8,
               budget_lakh: float = 50.0, delay_days: float = 7.0, seed0: int = 7000, workers: int | None = None,
               scenario: Scenario = Scenario(), log=lambda *_: None, progress=lambda *_: None,
               decompose: bool | str = "auto", prune: bool | str = "auto", refine_margin: int = 5) -> dict:
    """``decompose``: price each action on a twin of just the aircraft it can affect: its base (or the two bases
    of a transfer) under procedures where bases do not interact, else its aircraft type. Exact while repair
    depots are not saturated, and the chosen plan is verified on the whole fleet at the end. ``prune``: refine only actions within ``refine_margin`` of the
    best for some waiting aircraft. "auto" does both for fleets of 150 aircraft or more."""
    t0 = time.time()
    brd = board(world, start, dm, scenario=scenario)
    cands = candidates(world, start, dm, brd, horizon, scenario)
    log(f"  {len(cands)} candidate actions")
    seeds = list(range(seed0, seed0 + n_seeds))
    large = len(world.tails) >= 150
    if decompose == "auto":
        decompose = len(world.fleets) > 1 and large
    if prune == "auto":
        prune = large
    # where an action is priced: its base (or the two bases of a transfer) when bases do not interact under the
    # policy (repaired units return to the sender, no lending), else its aircraft type, else the whole fleet
    by_base = decompose and not (policy.lateral_transfer or policy.need_based_return)

    def view_of(a: Action):
        if not decompose:
            return None
        f = world.pns[a.pn].fleet
        if by_base and a.kind in ("cann", "expedite", "priority", "provision") and a.base:
            return (f, (a.base,))
        if by_base and a.kind == "transfer" and a.base and a.src:
            return (f, tuple(sorted({a.base, a.src})))
        return (f, None)

    runner = Runner(world, policy, horizon, start, dm, workers, scenario)
    try:
        progress(0, 4, "baseline futures")
        keys = [None] + sorted({view_of(c.action) for c in cands} - {None}, key=str)
        res = runner.run([(k, (), s) for k in keys for s in seeds])
        base_of = {k: res[i * n_seeds:(i + 1) * n_seeds] for i, k in enumerate(keys)}
        base = base_of[None]
        base_av = float(np.mean([r.overall_availability for r in base]))
        # 1) screen every candidate on the first futures
        progress(1, 4, f"screening {len(cands)} actions")
        jobs = [(view_of(c.action), (c.action,), s) for c in cands for s in seeds[:n_screen]]
        res = runner.run(jobs)
        promising = []
        for i, c in enumerate(cands):
            runs = res[i * n_screen:(i + 1) * n_screen]
            c.priced = _price(base_of[view_of(c.action)][:n_screen], runs)
            c.priced["grade"] = _grade(c.action.pn, n_fail, dq).grade
            if c.priced["mrv"] > 0 and c.priced["p_positive"] >= 0.5:
                promising.append((c, runs))
            else:
                c.priced["screened_out"] = True
        # an action can only be chosen if it is among the best for some aircraft it would return to service:
        # refine those (with a margin) and leave the rest as screened, which matters at fleet scale
        if prune:
            holes = defaultdict(int)
            for k, hs in brd["holes"].items():
                b, pn = k.split("|")
                holes[("hole", b, pn)] = len(hs)
            by_fix = defaultdict(list)
            for c, _ in promising:
                for f in c.fixes:
                    by_fix[f].append(c)
            keep = set()
            for f, cs in by_fix.items():
                cs.sort(key=lambda c: -c.priced["mrv"])
                keep.update(id(c) for c in cs[:holes.get(f, 1) + refine_margin])
            dropped = [(c, r) for c, r in promising if c.fixes and id(c) not in keep]
            for c, _ in dropped:
                c.priced["screened_out"] = True
                c.priced["outranked"] = True
            promising = [(c, r) for c, r in promising if not c.fixes or id(c) in keep]
            log(f"  {len(promising)} to refine ({len(dropped)} outranked for the same aircraft)")
        # 2) refine the promising ones on the remaining futures (same streams: paired)
        progress(2, 4, f"refining {len(promising)} actions")
        rest = seeds[n_screen:]
        res = runner.run([(view_of(c.action), (c.action,), s) for c, _ in promising for s in rest])
        for i, (c, first) in enumerate(promising):
            runs = first + res[i * len(rest):(i + 1) * len(rest)]
            grade = c.priced["grade"]
            c.priced = _price(base_of[view_of(c.action)], runs)
            c.priced["grade"] = grade
        n_refined = len(promising)
        # select: certain value, allowed evidence, resource conflicts, budget
        cap = defaultdict(int)
        for k, hs in brd["holes"].items():
            b, pn = k.split("|")
            cap[("hole", b, pn)] = len(hs)
        for k, v in start["stock"].items():
            cap[("stock",) + tuple(k)] = len(v)
        chosen, rejected, spent = [], [], 0.0
        order = sorted(cands, key=lambda c: -c.priced["mrv"])
        used = defaultdict(int)
        for c in order:
            pr = c.priced
            why = None
            if pr["grade"] in ("E4", "E5"):
                why = f"evidence {pr['grade']}: not recommended"
            elif pr.get("outranked"):
                why = "screened out: better actions exist for the same aircraft"
            elif pr.get("screened_out"):
                why = "screened out: no gain on the first futures"
            elif pr["ci95"][0] <= 0:
                why = "value not certain (95% CI includes zero)"
            elif pr["p_positive"] < 0.75:
                why = f"gains in only {pr['p_positive']:.0%} of futures"
            elif spent + c.action.cost_lakh > budget_lakh:
                why = "over the plan budget"
            else:
                for u in c.uses:
                    limit = cap.get(u, 1)
                    if used[u] + 1 > limit:
                        why = "conflicts with a better action (same spare, donor or unit)"
                for f in c.fixes:
                    if used[f] + 1 > cap.get(f, 0):
                        why = why or "the waiting aircraft are already covered by better actions"
            if why:
                rejected.append((c, why))
                continue
            for u in c.uses + c.fixes:
                used[u] += 1
            spent += c.action.cost_lakh
            chosen.append(c)

        # 3) joint verification of the whole plan, and the cost of a week's delay per item
        progress(3, 4, "verifying the plan")
        joint = None
        if chosen:
            acts = tuple(c.action for c in chosen)
            delayed = [(Action(**{**c.action.__dict__, "start_day": c.action.start_day + delay_days}),) for c in chosen]
            res = runner.run([(None, acts, s) for s in seeds]                       # the whole plan, whole fleet
                             + [(view_of(d[0]), d, s) for d in delayed for s in seeds])
            runs, rest = res[:n_seeds], res[n_seeds:]
            pj = _price(base, runs)
            joint = {"mrv": pj["mrv"], "ci95": pj["ci95"], "p_positive": pj["p_positive"],
                     "sum_of_parts": round(sum(c.priced["mrv"] for c in chosen), 1),
                     "availability_today_procedures": round(base_av, 4),
                     "availability_with_plan": round(float(np.mean([r.overall_availability for r in runs])), 4),
                     "nmcs_days_saved": round(float(np.mean([b.nmcs_days - a.nmcs_days
                                                             for a, b in zip(runs, base)])), 1)}
            for i, c in enumerate(chosen):
                later = _price(base_of[view_of(c.action)], rest[i * n_seeds:(i + 1) * n_seeds])
                c.priced["cod_per_day"] = round((c.priced["mrv"] - later["mrv"]) / delay_days, 2)
    finally:
        runner.close()

    def item(c: Candidate, why: str | None = None) -> dict:
        a, pr = c.action, c.priced
        grade_idx = {"E1": 0, "E2": 1, "E3": 2}.get(pr["grade"])
        auth = AUTHORITY[a.kind][grade_idx] if grade_idx is not None else "Not recommended"
        if a.kind == "provision" and a.cost_lakh > 25 and grade_idx is not None:
            auth = "Command logistics"
        d = {"kind": a.kind, "kind_label": KIND_LABEL[a.kind], "label": a.label(), "text": c.text,
             "reason": c.reason, "pn": a.pn, "part": world.pns[a.pn].name, "base": a.base,
             "fleet": world.pns[a.pn].fleet, "src": a.src, "tail": a.tail, "serial": a.serial,
             "agency": a.agency, "cost_lakh": a.cost_lakh, "authority": auth,
             **{k: v for k, v in pr.items() if k not in ("screened_out", "outranked")}}
        if why:
            d["not_selected"] = why
        return d

    return {
        "created": time.time(), "horizon_days": horizon, "seeds": n_seeds, "budget_lakh": budget_lakh,
        "policy": policy.name, "delay_days": delay_days,
        "items": [item(c) for c in chosen],
        "not_selected": [item(c, why) for c, why in sorted(rejected, key=lambda x: -x[0].priced["mrv"])],
        "joint": joint, "cost_lakh": round(spent, 2), "n_candidates": len(cands), "n_refined": n_refined,
        "scenario": [list(f) for f in scenario.forced],
        "screen_seeds": n_screen,
        "board": brd, "runtime_s": round(time.time() - t0, 1), "priced_by_fleet": bool(decompose),
    }


def action_from_item(d: dict) -> Action:
    return Action(d["kind"], d["pn"], base=d.get("base"), qty=1, agency=d.get("agency"),
                  cost_lakh=d.get("cost_lakh", 0.0), src=d.get("src"), serial=d.get("serial"), tail=d.get("tail"))


def simulate_plan(world: World, start: dict, dm: DecisionModel, policy: Policy, actions: tuple[Action, ...],
                  horizon: int = 90, seeds=range(7100, 7112), scenario: Scenario = Scenario()) -> tuple[list, list]:
    """Ensembles with and without the approved actions (same random streams)."""
    base = [Twin(world, policy, horizon, seed=s, decision_model=dm, start=start, resume=True,
                 scenario=scenario).run() for s in seeds]
    plan = [Twin(world, policy, horizon, seed=s, actions=actions, decision_model=dm, start=start, resume=True,
                 scenario=scenario).run() for s in seeds]
    return base, plan
