"""Sub-fleet views of the world and today's state, for pricing actions at scale.

Aircraft types share no part numbers: an action for one type changes another
type's future only through shared repair depots (whose capacity rarely binds)
and the plan budget (handled when selecting). A twin of just that type is then
a faithful and much cheaper place to price the action. Each aircraft keeps its
key in the full fleet, so it draws the same failures and turnarounds as there:
the sub-fleet's futures are the full fleet's futures for that type, except
where depot queues interact.
"""
from __future__ import annotations

from dataclasses import replace

from nirantar.bharat_fleet.world import World


def fleet_view(world: World, start: dict, fleets, bases=None) -> tuple[World, dict]:
    """The aircraft of ``fleets`` (at ``bases``, if given), their parts on the shelf and in the repair pipeline.

    A base view is exact for procedures where a repaired unit returns to the base that sent it and bases do not
    lend to each other (today's procedures, P0); the planner uses base views only for such policies."""
    fleets = set(fleets)
    keep_base = (lambda b: True) if bases is None else set(bases).__contains__
    tails = [{**t, "key": i} for i, t in enumerate(world.tails) if t["fleet"] in fleets and keep_base(t["base"])]
    ids = {t["id"] for t in tails}
    pns = {p: v for p, v in world.pns.items() if v.fleet in fleets}
    fl = {f: world.fleets[f] if bases is None else
          replace(world.fleets[f], tails_per_base={b: n for b, n in world.fleets[f].tails_per_base.items() if keep_base(b)})
          for f in fleets}
    w = replace(world, fleets=fl, pns=pns, tails=tails,
                initial_install={k: v for k, v in world.initial_install.items() if k[0] in ids},
                initial_stock={k: v for k, v in world.initial_stock.items() if k[1] in pns and keep_base(k[0])})
    s = dict(start)
    s["installed"] = {t: v for t, v in start["installed"].items() if t in ids}
    s["since_insp"] = {t: v for t, v in start["since_insp"].items() if t in ids}
    s["work_left"] = {t: v for t, v in start.get("work_left", {}).items() if t in ids}
    s["stock"] = {k: v for k, v in start["stock"].items() if tuple(k)[1] in pns and keep_base(tuple(k)[0])}
    s["pipeline"] = [it for it in start["pipeline"] if it.get("pn") in pns
                     and keep_base(it.get("from", it.get("base")))]
    s["waiting"] = [x for x in start.get("waiting", []) if x["tail"] in ids]
    # repair history only of the units this view holds (copying the whole fleet's per run would dominate)
    held = {sid for inst in s["installed"].values() for sid in inst.values()}
    held |= {sid for v in s["stock"].values() for sid in v} | {it["sid"] for it in s["pipeline"] if "sid" in it}
    s["hist"] = {k: v for k, v in start["hist"].items() if int(k) in held}
    return w, s
