"""Operations clock: run the station forward day by day, with and without the approved decisions.

Two copies of the fleet move through time on the *same* random events
(failures, repair times, supply regimes):

* **live**   - the approved plan actions are applied when the clock advances;
* **shadow** - nothing is applied (today's procedures only).

The gap between them is the readiness the approved decisions actually
bought, measured on identical events rather than estimated. Each advance
continues exactly from the previous state (remaining work, waiting times,
repair pipeline, supply regime).
"""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path

import numpy as np

from nirantar.bharat_fleet.world import World
from nirantar.sanjaya.twin import Action, Policy, Twin


def _daily(world: World, r) -> tuple[np.ndarray, np.ndarray]:
    """Whole-force availability and weighted aircraft-available-days for each simulated day."""
    counts = {f: len(world.tails_of(f)) for f in world.fleets}
    n = sum(counts.values())
    av = sum(r.fleet_daily_availability[f] * counts[f] for f in counts) / n
    waad = sum(r.fleet_daily_availability[f] * counts[f] * world.fleets[f].role_weight for f in counts)
    return av, waad


class OperationsClock:
    def __init__(self, world: World, policy: Policy, start: dict, path: str | Path, seed0: int = 9000):
        self.w, self.policy, self.path, self.seed0 = world, policy, Path(path), seed0
        if self.path.exists():
            with self.path.open("rb") as f:
                self.state = pickle.load(f)
        else:
            self.state = {"day": 0, "live": start, "shadow": start, "log": [], "events": [], "applied": []}

    @property
    def day(self) -> int:
        return int(self.state["day"])

    @property
    def snapshot(self) -> dict:
        return self.state["live"]

    def applied_seqs(self) -> set[int]:
        return {a["recommendation_seq"] for a in self.state["applied"] if a.get("recommendation_seq") is not None}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(self.state, f)
        os.replace(tmp, self.path)

    def advance(self, days: int, actions: tuple[Action, ...] = (), meta: tuple[dict, ...] = ()) -> dict:
        """Advance both fleets ``days`` days; ``actions`` (with ``meta`` for the log) go to the live fleet."""
        if not 1 <= days <= 30:
            raise ValueError("advance 1 to 30 days at a time")
        st, d0 = self.state, self.day
        seed = self.seed0 + d0
        live = Twin(self.w, self.policy, days, seed=seed, actions=actions, start=st["live"], record=True,
                    resume=True).run()
        shadow = Twin(self.w, self.policy, days, seed=seed, start=st["shadow"], record=True, resume=True).run()
        av_l, w_l = _daily(self.w, live)
        av_s, w_s = _daily(self.w, shadow)
        for i in range(days):
            st["log"].append({"day": d0 + i + 1, "live": round(float(av_l[i]), 4), "shadow": round(float(av_s[i]), 4),
                              "live_waad": round(float(w_l[i]), 3), "shadow_waad": round(float(w_s[i]), 3)})

        events = []
        for a, m in zip(actions, meta):
            events.append({"day": d0, "kind": "applied", "text": f"Applied: {m.get('text', a.label())}",
                           "tail": a.tail, "base": a.base})
            st["applied"].append({"day": d0, "label": a.label(), **m})
        names = {p: v.name for p, v in self.w.pns.items()}
        for s in live.records["snags"]:
            events.append({"day": d0 + int(np.ceil(s["day"])) if s["day"] > 0 else d0 + 1, "kind": "failure",
                           "tail": s["tail"], "base": s["base"],
                           "text": f"{s['tail']}: {s['text']}"})
        before = {w["tail"] for w in st["live"].get("waiting", [])}
        after_w = {w["tail"]: w for w in live.snapshot.get("waiting", [])}
        for t in sorted(before - set(after_w)):
            events.append({"day": d0 + days, "kind": "restored", "tail": t, "base": t.split("-")[1],
                           "text": f"{t}: all parts fitted, back on the line"})
        for t in sorted(set(after_w) - before):
            w = after_w[t]
            name = names[w["pn"]]
            name = name if name[1].isupper() else name[0].lower() + name[1:]
            events.append({"day": d0 + days, "kind": "waiting", "tail": t, "base": t.split("-")[1],
                           "text": f"{t}: waiting for {name}"})
        events.sort(key=lambda e: (e["day"], {"applied": 0, "failure": 1, "waiting": 2, "restored": 3}[e["kind"]]))
        st["events"].extend(events)
        st["live"], st["shadow"] = live.snapshot, shadow.snapshot
        st["day"] = d0 + days
        self._save()
        return {"day": st["day"], "new_events": len(events), "applied": len(actions)}

    def view(self, n_events: int = 150) -> dict:
        st = self.state
        log = st["log"]
        gained = sum(r["live_waad"] - r["shadow_waad"] for r in log)
        waiting_live = len({w["tail"] for w in st["live"].get("waiting", [])})
        waiting_shadow = len({w["tail"] for w in st["shadow"].get("waiting", [])})
        return {
            "day": self.day, "log": log, "events": st["events"][-n_events:][::-1], "applied": st["applied"][::-1],
            "events_total": len(st["events"]),
            "waad_gained": round(gained, 1),
            "aircraft_days_gained": round(sum((r["live"] - r["shadow"]) for r in log) * len(self.w.tails), 1),
            "waiting_live": waiting_live, "waiting_shadow": waiting_shadow,
            "availability_live": log[-1]["live"] if log else None,
            "availability_shadow": log[-1]["shadow"] if log else None,
        }

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
