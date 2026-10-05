"""SANJAYA: Sustainment Digital Twin (event-driven discrete-event simulation).

The twin simulates a sustainment enterprise built from a BHARAT-FLEET world:
tails flying, serialised parts ageing and failing (Weibull + Kijima virtual
age + frailty), inspections, base stores, backorders, repair agencies with
capacity and quality, supply regimes, and policy decisions.

Random draws are *keyed* by entity (serial, installation count, repair count,
...) rather than taken from one shared stream. Two runs with the same seed
therefore see the same "physics" even if a policy or action changes the order
of events. These common random numbers make paired comparisons (MRV) precise.
"""
from __future__ import annotations

import heapq
import math
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np

from nirantar.bharat_fleet.world import Agency, World

# ---------------------------------------------------------------- randomness


def _key(x) -> int:
    if isinstance(x, (int, np.integer)):
        return int(x) & 0xFFFFFFFF
    return zlib.crc32(str(x).encode())


def krng(*keys) -> np.random.Generator:
    """A generator determined only by its keys (common random numbers)."""
    return np.random.default_rng(np.random.SeedSequence([_key(k) for k in keys]))


# ---------------------------------------------------------------- inputs


class DecisionModel(Protocol):
    """What policies may know: *estimated* reliability, not the truth."""

    q_hat: dict[str, float]
    rogue_flags: set[int]

    def fail_prob(self, pn: str, env: str, age_fh: float, horizon_fh: float) -> float: ...

    def cum_hazard(self, pn: str, env: str, a0: float, a1: float) -> float: ...


@dataclass
class Policy:
    name: str
    predictive_swap: bool = False      # replace high-risk parts during inspections
    swap_threshold: float = 0.35
    lateral_transfer: bool = False     # borrow a spare from a sister base
    need_based_return: bool = False    # ship repaired units to the neediest base
    aog_priority: bool = False         # agencies repair back-ordered PNs first
    smart_routing: bool = False        # route by expected total downtime (uses q_hat)
    rogue_quarantine: bool = False     # deep-strip flagged rogue serials
    routing_mix: float = 0.0           # share of carcasses sent ad hoc to another eligible agency


@dataclass(frozen=True)
class Action:
    """A sustainment action applied at the start of a run (CHANAKYA catalogue)."""
    kind: str                          # provision | route | indigenise
    pn: str
    base: Optional[str] = None
    qty: int = 1
    agency: Optional[str] = None
    start_day: float = 0.0             # when the action takes effect / is ordered
    cost_lakh: float = 0.0

    def label(self) -> str:
        if self.kind == "provision":
            return f"PROVISION {self.qty}x {self.pn} @ {self.base} (day {self.start_day:g})"
        if self.kind == "route":
            return f"ROUTE {self.pn} -> {self.agency} (day {self.start_day:g})"
        if self.kind == "indigenise":
            return f"INDIGENISE {self.pn} via {self.agency} (qualified day {self.start_day:g})"
        return f"{self.kind} {self.pn}"


@dataclass(frozen=True)
class Scenario:
    name: str = "normal"
    forced: tuple[tuple[str, str, float, float], ...] = ()   # (country, state, start, end)


SUPPLY_SHOCK = Scenario("supply_shock", (("RU", "disrupted", 20.0, 200.0),))

OVERHAUL_LIMIT = 1.2        # overhaul once hours since last overhaul exceed 1.2 x eta

INDIGENOUS_AGENCY = Agency("IND-V", "MSME", "IN", 0.35, 20, 0.30, 6, 3)

# ---------------------------------------------------------------- results


@dataclass
class RunResult:
    policy: str
    scenario: str
    seed: int
    horizon: int
    fleet_daily_availability: dict[str, np.ndarray]
    mean_availability: dict[str, float]
    overall_availability: float
    aad: float                          # aircraft-available-days
    waad: float                         # weighted AAD
    nmcs_days: float
    nmcm_days: float
    failures: int
    preventive_swaps: int
    repairs_by_agency: dict[str, int]
    spend_lakh: float
    nmcs_by_tail: dict[str, float]
    records: Optional[dict] = None
    snapshot: Optional[dict] = None


# ---------------------------------------------------------------- the twin


class Twin:
    MC, NMCM, NMCS = 0, 1, 2

    def __init__(
        self,
        world: World,
        policy: Policy,
        horizon_days: int,
        seed: int,
        scenario: Scenario = Scenario(),
        actions: tuple[Action, ...] = (),
        decision_model: Optional[DecisionModel] = None,
        start: Optional[dict] = None,
        record: bool = False,
        type_weights: Optional[dict[str, float]] = None,
    ):
        if (policy.predictive_swap or policy.smart_routing or policy.rogue_quarantine) and decision_model is None:
            raise ValueError(f"policy {policy.name} needs a decision model")
        self.w = world
        self.policy = policy
        self.H = float(horizon_days)
        self.seed = seed
        self.scenario = scenario
        self.actions = actions
        self.dm = decision_model
        self.record = record
        self.type_weights = type_weights or {f: ft.role_weight for f, ft in world.fleets.items()}

        self.agencies = dict(world.agencies)
        self.agencies[INDIGENOUS_AGENCY.id] = INDIGENOUS_AGENCY
        self.eligible = {pn: list(p.eligible_agencies) for pn, p in world.pns.items()}
        self.default_agency = {pn: p.default_agency for pn, p in world.pns.items()}
        self.routing_override: dict[str, str] = {}

        self._events: list = []
        self._seq = 0
        self.t = 0.0
        self._init_regimes((start or {}).get("regimes", {}))
        self._init_state(start)
        self._apply_actions()

    # ------------------------------------------------------------ setup

    def _init_regimes(self, initial: dict[str, int] | None = None) -> None:
        n_days = int(self.H) + 2
        self.regime_state: dict[str, np.ndarray] = {}
        for c, m in self.w.regimes.items():
            states = np.zeros(n_days, dtype=int)
            states[0] = int((initial or {}).get(c, 0))     # continue from the regime history ended in
            if len(m.states) > 1:
                g = krng(self.seed, "regime", c)
                u = g.random(n_days)
                P = np.cumsum(np.array(m.transition), axis=1)
                for d in range(1, n_days):
                    states[d] = int(np.searchsorted(P[states[d - 1]], u[d]))
            for country, state, s, e in self.scenario.forced:
                if country == c:
                    idx = m.states.index(state)
                    states[int(s):min(int(e), n_days)] = idx
            self.regime_state[c] = states

    def regime_multiplier(self, country: str, t: float) -> float:
        m = self.w.regimes.get(country)
        if m is None:
            return 1.0
        d = min(int(t), len(self.regime_state[country]) - 1)
        return m.tat_multiplier[self.regime_state[country][d]]

    def _init_state(self, start: Optional[dict]) -> None:
        w = self.w
        n = len(w.serials)
        self.V = np.zeros(n)                       # true virtual age
        self.X = np.zeros(n)                       # FH since last repair
        self.z = np.array([s.frailty for s in w.serials], dtype=float)
        self.hist: dict[int, list[tuple[str, float]]] = defaultdict(list)   # (agency, X) per repair
        self.install_count = np.zeros(n, dtype=int)
        self.repair_count = np.zeros(n, dtype=int)
        self.stock: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.backorders: dict[tuple[str, str], deque] = defaultdict(deque)
        self.queues: dict[str, list] = defaultdict(list)
        self.busy: dict[str, int] = defaultdict(int)
        self.spend = 0.0
        self.failures = 0
        self.preventive = 0
        self.repairs_by_agency: dict[str, int] = defaultdict(int)
        self._job_seq = 0

        self.tails = []
        for i, t in enumerate(w.tails):
            ft = w.fleets[t["fleet"]]
            slots = [(p.pn, k) for p in w.pns.values() if p.fleet == t["fleet"] for k in range(p.positions)]
            self.tails.append({
                "idx": i, "id": t["id"], "fleet": t["fleet"], "base": t["base"],
                "env": w.base_env(t["base"]), "rate": ft.fh_per_day, "ft": ft,
                "slots": slots, "inst": {}, "rem": {}, "since_insp": 0.0,
                "work_until": 0.0, "last_t": 0.0, "flying": False, "ver": 0,
                "state": None, "state_since": 0.0, "spell": {}, "n_inst": {},
            })
        self.intervals: dict[int, list[tuple[float, float, int]]] = defaultdict(list)

        # records
        self.spells: list[dict] = []
        self.repairs: list[dict] = []
        self.snags: list[dict] = []

        if start is None:
            for (tail_id, pn, k), sid in w.initial_install.items():
                tail = self._tail_by_id(tail_id)
                self.X[sid] = w.initial_tso_fh[sid]
                tail["inst"][(pn, k)] = sid
            for key, sids in w.initial_stock.items():
                self.stock[key] = list(sids)
            for tail in self.tails:
                tail["since_insp"] = float(krng(self.seed, "insp0", tail["idx"]).uniform(0, tail["ft"].inspection_interval_fh))
        else:
            self._load_snapshot(start)

        for tail in self.tails:
            for slot, sid in tail["inst"].items():
                self._begin_spell(tail, slot, sid, prev_agency=self._prev_agency(sid))
                tail["rem"][slot] = self._sample_life(tail, sid, slot)
            for slot in tail["slots"]:
                if slot not in tail["inst"]:
                    self.backorders[(tail["base"], slot[0])].append((tail["idx"], slot, 0.0))
            self._refresh(tail)

        if start is not None:
            for item in start["pipeline"]:
                item = dict(item)
                kind, dt = item.pop("type"), item.pop("dt", 0.0)
                if kind == "arrive":
                    self._push(dt, "ARRIVE", (item["base"], item["sid"]))
                elif kind == "inrepair":
                    item["start"] = 0.0
                    self.busy[item["agency"]] += 1
                    self._push(dt, "REPAIR_DONE", item)
                else:
                    self._push(dt, "AG_ARRIVE", item)
            for key in list(self.backorders):
                self._try_fill(key[0], key[1])

    def _tail_by_id(self, tail_id: str) -> dict:
        if not hasattr(self, "_tail_index"):
            self._tail_index = {t["id"]: t for t in self.tails}
        return self._tail_index[tail_id]

    def _prev_agency(self, sid: int) -> str:
        h = self.hist.get(sid)
        if not h:
            return "UNKNOWN"
        g, _x, kind = h[-1]
        return g + "#OH" if kind == "OH" else g

    def _load_snapshot(self, s: dict) -> None:
        self.V[:] = s["V"]
        self.X[:] = s["X"]
        self.z[:] = s["z"]
        self.hist = defaultdict(list, {int(k): [tuple(e) for e in v] for k, v in s["hist"].items()})
        for tail in self.tails:
            for slot, sid in s["installed"].get(tail["id"], {}).items():
                tail["inst"][tuple(slot)] = sid
            tail["since_insp"] = s["since_insp"].get(tail["id"], 0.0)
        for key, sids in s["stock"].items():
            self.stock[tuple(key)] = list(sids)

    def _apply_actions(self) -> None:
        for a in self.actions:
            if a.kind == "provision":
                p = self.w.pns[a.pn]
                for j in range(a.qty):
                    sid = self._new_serial(a.pn)
                    g = krng(self.seed, "proc", a.pn, a.base, j, a.start_day)
                    origin = "IN" if self.default_agency.get(a.pn) == INDIGENOUS_AGENCY.id else p.origin
                    lead = p.procurement_days * float(np.exp(g.normal(0, 0.3)))
                    lead *= self.regime_multiplier(origin, a.start_day)
                    self._push(a.start_day + lead, "ARRIVE", (a.base, sid))
                self.spend += a.cost_lakh
            elif a.kind == "route":
                self._push(a.start_day, "ROUTE", (a.pn, a.agency))
            elif a.kind == "indigenise":
                self._push(a.start_day, "INDIGENISE", (a.pn, a.agency or INDIGENOUS_AGENCY.id))
                self.spend += a.cost_lakh
            else:
                raise ValueError(a.kind)

    def _new_serial(self, pn: str) -> int:
        sid = len(self.V)
        self.V = np.append(self.V, 0.0)
        self.X = np.append(self.X, 0.0)
        self.z = np.append(self.z, 1.0)
        self.install_count = np.append(self.install_count, 0)
        self.repair_count = np.append(self.repair_count, 0)
        if not hasattr(self, "new_pn"):
            self.new_pn: dict[int, str] = {}
        self.new_pn[sid] = pn
        return sid

    def pn_of(self, sid: int) -> str:
        if sid < len(self.w.serials):
            return self.w.serials[sid].pn
        return self.new_pn[sid]

    # ------------------------------------------------------------ events

    def _push(self, t: float, kind: str, payload) -> None:
        self._seq += 1
        heapq.heappush(self._events, (t, self._seq, kind, payload))

    def run(self) -> RunResult:
        while self._events and self._events[0][0] <= self.H:
            t, _, kind, payload = heapq.heappop(self._events)
            self.t = t
            getattr(self, "_on_" + kind)(payload)
        self.t = self.H
        for tail in self.tails:
            self._age(tail, self.H)
            self._close_state(tail, self.H)
        return self._result()

    # ------------------------------------------------------------ physics

    def _sample_life(self, tail: dict, sid: int, slot) -> float:
        """Remaining FH until failure, conditional on current effective age.

        The uniform draw is keyed by (tail, slot, n-th installation in that slot),
        not by serial: two runs that fit different serials into the same slot
        still share the slot's random stream, which keeps paired runs coupled.
        """
        pn = self.pn_of(sid)
        p = self.w.pns[pn]
        eta = self.w.eta_true(pn, tail["env"])
        A = self.V[sid] + self.X[sid]
        n = tail["n_inst"].get(slot, 0)
        tail["n_inst"][slot] = n + 1
        u = krng(self.seed, "life", tail["idx"], slot[0], slot[1], n).random()
        self.install_count[sid] += 1
        total = eta * ((A / eta) ** p.beta + (-math.log(max(u, 1e-300))) / self.z[sid]) ** (1.0 / p.beta)
        return max(total - A, 1e-6)

    def _age(self, tail: dict, t: float) -> None:
        dt = t - tail["last_t"]
        if dt > 0 and tail["flying"]:
            fh = dt * tail["rate"]
            for slot, sid in tail["inst"].items():
                tail["rem"][slot] -= fh
                self.X[sid] += fh
            tail["since_insp"] += fh
        tail["last_t"] = t

    def _is_mc(self, tail: dict) -> bool:
        return self.t >= tail["work_until"] - 1e-9 and len(tail["inst"]) == len(tail["slots"])

    def _refresh(self, tail: dict) -> None:
        """Recompute state and schedule the tail's next event."""
        self._age(tail, self.t)
        tail["ver"] += 1
        if self._is_mc(tail):
            self._set_state(tail, self.MC)
            tail["flying"] = True
            rate = tail["rate"]
            slot = min(tail["rem"], key=tail["rem"].get)
            t_fail = self.t + max(tail["rem"][slot], 0.0) / rate
            t_insp = self.t + max(tail["ft"].inspection_interval_fh - tail["since_insp"], 0.0) / rate
            if t_fail <= t_insp:
                self._push(t_fail, "FAIL", (tail["idx"], tail["ver"], slot))
            else:
                self._push(t_insp, "INSPECT", (tail["idx"], tail["ver"]))
        else:
            tail["flying"] = False
            empty = len(tail["inst"]) < len(tail["slots"])
            self._set_state(tail, self.NMCS if (empty and self.t >= tail["work_until"] - 1e-9) else self.NMCM)
            if self.t < tail["work_until"]:
                self._push(tail["work_until"], "WORKDONE", (tail["idx"], tail["ver"]))

    def _set_state(self, tail: dict, state: int) -> None:
        if tail["state"] == state:
            return
        if tail["state"] is not None:
            self.intervals[tail["idx"]].append((tail["state_since"], self.t, tail["state"]))
        tail["state"] = state
        tail["state_since"] = self.t

    def _close_state(self, tail: dict, t: float) -> None:
        if tail["state"] is not None and t > tail["state_since"]:
            self.intervals[tail["idx"]].append((tail["state_since"], t, tail["state"]))
        tail["state_since"] = t

    # ------------------------------------------------------------ records

    def _begin_spell(self, tail: dict, slot, sid: int, prev_agency: str) -> None:
        if self.record:
            tail["spell"][slot] = {
                "serial": sid, "pn": self.pn_of(sid), "tail": tail["id"], "fleet": tail["fleet"],
                "base": tail["base"], "env": tail["env"], "install_day": self.t,
                "entry_fh": float(self.X[sid]), "prev_agency": prev_agency,
                "n_prior_repairs": len(self.hist.get(sid, [])),
            }

    def _end_spell(self, tail: dict, slot, sid: int, reason: Optional[str]) -> None:
        if self.record and slot in tail["spell"]:
            sp = tail["spell"].pop(slot)
            sp.update({"removal_day": self.t if reason else np.nan, "exit_fh": float(self.X[sid]),
                       "removal_reason": reason})
            self.spells.append(sp)

    def _snag(self, tail: dict, sid: int, slot) -> None:
        if not self.record:
            return
        pn = self.pn_of(sid)
        fam = self.w.pns[pn].family
        modes = dict(self.w.failure_modes[fam])
        boost = self.w.env_mode_boost.get((fam, tail["env"]))
        if boost:
            modes[boost] = modes.get(boost, 0.1) * 3.0
        names = list(modes)
        p = np.array([modes[m] for m in names])
        p = p / p.sum()
        g = krng(self.seed, "mode", tail["idx"], slot[0], slot[1], tail["n_inst"].get(slot, 0))
        mode = names[int(np.searchsorted(np.cumsum(p), g.random()))]
        self.snags.append({
            "day": self.t, "tail": tail["id"], "fleet": tail["fleet"], "base": tail["base"],
            "env": tail["env"], "pn": pn, "family": fam, "serial": sid, "mode": mode,
            "text": f"{self.w.pns[pn].name} pos {slot[1] + 1}: {mode.replace('_', ' ')} found on post-flight",
        })

    # ------------------------------------------------------------ handlers

    def _on_FAIL(self, payload) -> None:
        idx, ver, slot = payload
        tail = self.tails[idx]
        if ver != tail["ver"]:
            return
        self._age(tail, self.t)
        sid = tail["inst"].pop(slot)
        tail["rem"].pop(slot, None)
        self.failures += 1
        self._snag(tail, sid, slot)
        self._end_spell(tail, slot, sid, "failure")
        tail["work_until"] = max(tail["work_until"], self.t + tail["ft"].mttr_fail_days)
        self._send_for_repair(sid, tail["base"])
        self.backorders[(tail["base"], slot[0])].append((idx, slot, self.t))
        self._try_fill(tail["base"], slot[0])
        self._refresh(tail)

    def _on_INSPECT(self, payload) -> None:
        idx, ver = payload
        tail = self.tails[idx]
        if ver != tail["ver"]:
            return
        self._age(tail, self.t)
        tail["since_insp"] = 0.0
        tail["work_until"] = max(tail["work_until"], self.t + tail["ft"].inspection_days)
        if self.policy.predictive_swap:
            for slot in list(tail["inst"]):
                sid = tail["inst"][slot]
                pn = slot[0]
                key = (tail["base"], pn)
                if not self.stock[key]:
                    continue
                age = self.est_age(sid)
                p = self.dm.fail_prob(pn, tail["env"], age, tail["ft"].inspection_interval_fh)
                if p > self.policy.swap_threshold:
                    tail["inst"].pop(slot)
                    tail["rem"].pop(slot, None)
                    self._end_spell(tail, slot, sid, "preventive")
                    self.preventive += 1
                    self._send_for_repair(sid, tail["base"])
                    self._install(tail, slot, self.stock[key].pop(0), swap_time=0.0)
        self._refresh(tail)

    def _on_WORKDONE(self, payload) -> None:
        idx, ver = payload
        tail = self.tails[idx]
        if ver != tail["ver"]:
            return
        self._refresh(tail)

    def _install(self, tail: dict, slot, sid: int, swap_time: float) -> None:
        tail["inst"][slot] = sid
        self._begin_spell(tail, slot, sid, prev_agency=self._prev_agency(sid))
        tail["rem"][slot] = self._sample_life(tail, sid, slot)
        tail["work_until"] = max(tail["work_until"], self.t + swap_time)

    def _try_fill(self, base: str, pn: str) -> None:
        key = (base, pn)
        while self.backorders[key] and self.stock[key]:
            idx, slot, _ = self.backorders[key].popleft()
            tail = self.tails[idx]
            self._age(tail, self.t)
            self._install(tail, slot, self.stock[key].pop(0), tail["ft"].mttr_swap_days)
            self._refresh(tail)
        if self.backorders[key] and self.policy.lateral_transfer:
            fleet = self.w.pns[pn].fleet
            pending = getattr(self, "_lateral_pending", defaultdict(int))
            self._lateral_pending = pending
            need = len(self.backorders[key]) - pending[key]
            for other in self.w.fleets[fleet].tails_per_base:
                if need <= 0:
                    break
                okey = (other, pn)
                if other == base or self.backorders[okey]:
                    continue
                while self.stock[okey] and need > 0:
                    sid = self.stock[okey].pop(0)
                    pending[key] += 1
                    need -= 1
                    self._push(self.t + 2.0, "ARRIVE", (base, sid, "lateral"))

    def _on_ARRIVE(self, payload) -> None:
        base, sid = payload[0], payload[1]
        pn = self.pn_of(sid)
        if len(payload) > 2 and payload[2] == "lateral":
            self._lateral_pending[(base, pn)] -= 1
        self.stock[(base, pn)].append(sid)
        self._try_fill(base, pn)

    def _on_ROUTE(self, payload) -> None:
        pn, agency = payload
        self.routing_override[pn] = agency

    def _on_INDIGENISE(self, payload) -> None:
        pn, agency = payload
        if agency not in self.eligible[pn]:
            self.eligible[pn].append(agency)
        self.default_agency[pn] = agency
        self.routing_override[pn] = agency

    # ------------------------------------------------------------ repair network

    def choose_agency(self, sid: int, pn: str, env: str = "temperate") -> str:
        if pn in self.routing_override:
            return self.routing_override[pn]
        if not self.policy.smart_routing:
            if self.policy.routing_mix > 0 and len(self.eligible[pn]) > 1:
                g = krng(self.seed, "mix", sid, self.repair_count[sid])
                if g.random() < self.policy.routing_mix:
                    others = [a for a in self.eligible[pn] if a != self.default_agency[pn]]
                    return others[int(g.integers(len(others)))]
            return self.default_agency[pn]
        best, best_cost = None, float("inf")
        for g in self.eligible[pn]:
            ag = self.agencies[g]
            backlog = max(0, len(self.queues[g]) + self.busy[g] - ag.servers + 1) / ag.servers
            tat = ag.tat_median_days * (1 + backlog)
            pipeline = tat + 2 * self.transit_days(g)
            q = self.dm.q_hat.get(g, ag.q)
            v_after = self.est_virtual_age(sid) + q * self.X[sid]
            exp_fail = self.dm.cum_hazard(pn, env, v_after, v_after + 300.0)
            cost = pipeline + 25.0 * exp_fail
            if cost < best_cost:
                best, best_cost = g, cost
        return best

    def transit_days(self, g: str) -> float:
        """One-way shipping time; supply regimes stretch foreign shipping/customs/payment."""
        ag = self.agencies[g]
        return ag.transport_days * self.regime_multiplier(ag.country, self.t)

    def _send_for_repair(self, sid: int, from_base: str) -> None:
        pn = self.pn_of(sid)
        deep = bool(self.policy.rogue_quarantine and sid in self.dm.rogue_flags)
        g = self.choose_agency(sid, pn, self.w.base_env(from_base))
        if deep:
            g = min(self.eligible[pn], key=lambda a: self.agencies[a].q)
        self._job_seq += 1
        overhaul = (not deep) and self.X[sid] + self._recorded_virtual_age(sid) >= OVERHAUL_LIMIT * self.w.pns[pn].eta
        job = {"sid": sid, "pn": pn, "agency": g, "from": from_base, "sent": self.t,
               "deep": deep, "overhaul": bool(overhaul), "id": self._job_seq}
        self._push(self.t + self.transit_days(g), "AG_ARRIVE", job)

    def _on_AG_ARRIVE(self, job: dict) -> None:
        self.queues[job["agency"]].append(job)
        self._start_jobs(job["agency"])

    def _pick_job(self, g: str) -> dict:
        q = self.queues[g]
        if self.policy.aog_priority and len(q) > 1:
            def need(j):
                return sum(len(self.backorders[(b, j["pn"])]) for b in self.w.bases)
            best = max(range(len(q)), key=lambda i: (need(q[i]), -i))
            return q.pop(best)
        return q.pop(0)

    def _start_jobs(self, g: str) -> None:
        ag = self.agencies[g]
        while self.queues[g] and self.busy[g] < ag.servers:
            job = self._pick_job(g)
            self.busy[g] += 1
            sid = job["sid"]
            r = krng(self.seed, "tat", sid, self.repair_count[sid], g)
            tat = ag.tat_median_days * float(np.exp(r.normal(0.0, ag.tat_sigma)))
            if job["deep"] or job.get("overhaul"):
                tat *= 1.5
            job["start"] = self.t
            self._push(self.t + tat, "REPAIR_DONE", job)

    def _on_REPAIR_DONE(self, job: dict) -> None:
        g, sid = job["agency"], job["sid"]
        self.busy[g] -= 1
        self.repair_count[sid] += 1
        self.repairs_by_agency[g] += 1
        x = float(self.X[sid])
        overhaul = bool(job.get("overhaul"))
        if job["deep"]:
            self.V[sid] = 0.0
            self.z[sid] = 1.0
        elif overhaul:
            self.V[sid] = 0.0                                      # hard-time overhaul resets age
        else:
            self.V[sid] = self.V[sid] + self.agencies[g].q * x      # Kijima type I
        self.hist[sid].append((g, x, "OH" if (overhaul or job["deep"]) else "R"))
        self.X[sid] = 0.0
        if self.record:
            self.repairs.append({"serial": sid, "pn": job["pn"], "agency": g, "sent_day": job["sent"],
                                 "start_day": job["start"], "done_day": self.t, "deep_strip": job["deep"],
                                 "overhaul": overhaul, "from_base": job["from"], "fh_since_repair": x})
        dest = self._destination(job)
        self._push(self.t + self.transit_days(g), "ARRIVE", (dest, sid))
        self._start_jobs(g)

    def _destination(self, job: dict) -> str:
        if not self.policy.need_based_return:
            return job["from"]
        pn = job["pn"]
        bases = list(self.w.fleets[self.w.pns[pn].fleet].tails_per_base)
        return max(bases, key=lambda b: (len(self.backorders[(b, pn)]), -len(self.stock[(b, pn)]), b == job["from"]))

    # ------------------------------------------------------------ estimation helpers for policies

    def est_virtual_age(self, sid: int) -> float:
        v = 0.0
        for g, x, kind in self.hist.get(sid, []):
            v = 0.0 if kind == "OH" else v + self.dm.q_hat.get(g, 0.3) * x
        return v

    def _recorded_virtual_age(self, sid: int) -> float:
        """Hours since last overhaul (what a TSO-based hard-time rule sees)."""
        v = 0.0
        for _g, x, kind in self.hist.get(sid, []):
            v = 0.0 if kind == "OH" else v + x
        return v

    def est_age(self, sid: int) -> float:
        return self.est_virtual_age(sid) + float(self.X[sid])

    # ------------------------------------------------------------ outputs

    def snapshot(self) -> dict:
        """State to continue from (pipeline items restart at their agency)."""
        pipeline = []
        for t, _, kind, payload in self._events:
            if kind == "AG_ARRIVE":
                job = dict(payload)
                pipeline.append({"type": "job", **job, "dt": max(t - self.H, 0.0)})
            elif kind == "REPAIR_DONE":
                job = dict(payload)
                job.pop("start", None)
                pipeline.append({"type": "inrepair", **job, "dt": max(t - self.H, 0.0)})
            elif kind == "ARRIVE":
                base, sid = payload[0], payload[1]
                pipeline.append({"type": "arrive", "base": base, "sid": sid, "pn": self.pn_of(sid),
                                 "dt": max(t - self.H, 0.0)})
        for g, q in self.queues.items():
            pipeline.extend({"type": "job", **j, "dt": 0.0} for j in q)
        return {
            "V": self.V.copy(), "X": self.X.copy(), "z": self.z.copy(),
            "hist": {k: list(v) for k, v in self.hist.items()},
            "installed": {t["id"]: dict(t["inst"]) for t in self.tails},
            "since_insp": {t["id"]: t["since_insp"] for t in self.tails},
            "stock": {k: list(v) for k, v in self.stock.items() if v},
            "pipeline": pipeline,
            "regimes": {c: int(st[min(int(self.H), len(st) - 1)]) for c, st in self.regime_state.items()},
        }

    def _result(self) -> RunResult:
        H = int(self.H)
        daily = {f: np.zeros(H) for f in self.w.fleets}
        counts = defaultdict(int)
        nmcs = nmcm = 0.0
        nmcs_by_tail: dict[str, float] = defaultdict(float)
        for tail in self.tails:
            counts[tail["fleet"]] += 1
            for s, e, st in self.intervals[tail["idx"]]:
                if st == self.MC:
                    _accumulate(daily[tail["fleet"]], s, e)
                elif st == self.NMCS:
                    nmcs += e - s
                    nmcs_by_tail[tail["id"]] += e - s
                else:
                    nmcm += e - s
        fleet_avail = {f: daily[f] / max(counts[f], 1) for f in daily}
        mean_av = {f: float(v.mean()) for f, v in fleet_avail.items()}
        aad = float(sum(v.sum() for v in daily.values()))
        waad = float(sum(self.type_weights.get(f, 1.0) * v.sum() for f, v in daily.items()))
        total_tails = sum(counts.values())
        records = None
        if self.record:
            open_spells = []
            for tail in self.tails:
                for slot, sp in list(tail["spell"].items()):
                    sid = tail["inst"].get(slot)
                    if sid is not None:
                        sp = dict(sp)
                        sp.update({"removal_day": np.nan, "exit_fh": float(self.X[sid]), "removal_reason": None})
                        open_spells.append(sp)
            in_progress = []
            for item in self.snapshot()["pipeline"]:
                if item["type"] in ("job", "inrepair"):
                    in_progress.append({"serial": item["sid"], "pn": item["pn"], "agency": item["agency"],
                                        "sent_day": item["sent"], "start_day": np.nan, "done_day": np.nan,
                                        "deep_strip": item["deep"], "overhaul": item.get("overhaul", False),
                                        "from_base": item["from"], "fh_since_repair": np.nan})
            records = {"spells": self.spells + open_spells, "repairs": self.repairs + in_progress,
                       "snags": self.snags}
        return RunResult(
            policy=self.policy.name, scenario=self.scenario.name, seed=self.seed, horizon=H,
            fleet_daily_availability=fleet_avail, mean_availability=mean_av,
            overall_availability=aad / (total_tails * H), aad=aad, waad=waad,
            nmcs_days=nmcs, nmcm_days=nmcm, failures=self.failures, preventive_swaps=self.preventive,
            repairs_by_agency=dict(self.repairs_by_agency), spend_lakh=self.spend,
            nmcs_by_tail=dict(nmcs_by_tail), records=records,
            snapshot=self.snapshot() if self.record else None,
        )


def _accumulate(arr: np.ndarray, s: float, e: float) -> None:
    """Add the overlap of [s, e) with each unit day bin to arr."""
    n = len(arr)
    s, e = max(s, 0.0), min(e, float(n))
    if e <= s:
        return
    d0, d1 = int(s), int(math.ceil(e)) - 1
    if d0 == d1:
        arr[d0] += e - s
        return
    arr[d0] += (d0 + 1) - s
    if d1 > d0 + 1:
        arr[d0 + 1:d1] += 1.0
    arr[d1] += e - d1
