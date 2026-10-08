"""Larger synthetic fleets for scale testing (the default 70-aircraft world is unchanged).

``make_scaled_world(n_fleets, n_bases, squadrons_per_fleet, pns_per_fleet)``
builds up to six aircraft types stationed at several bases each, with generated
part catalogues (families, origins, approved agencies, reliability) and depot
capacity grown with the fleet, so that queues reflect the same utilisation as
the default world rather than an overloaded one.
"""
from __future__ import annotations

import math

import numpy as np

from nirantar.bharat_fleet.world import (Agency, Base, FleetType, PartNumber, Serial, World, default_agencies,
                                         default_regimes, make_world)

ENVS = ("coastal_saline", "desert_dust", "high_altitude", "humid_ne", "plains")
# id, prefix, role, squadron size, FH/day, inspection interval, inspection days, MTTR fail, MTTR swap, weight, origin mix
TYPES = [
    ("FighterH", "FI", "heavy fighter", 18, 0.9, 150, 3, 2.0, 0.5, 1.0, {"RU": 0.7, "IN": 0.3}),
    ("HeloU", "HE", "utility helicopter", 12, 0.8, 120, 2, 1.5, 0.5, 0.7, {"FR": 0.4, "IN": 0.6}),
    ("FighterL", "LF", "light fighter", 18, 0.8, 150, 3, 1.8, 0.5, 0.9, {"IN": 0.7, "FR": 0.3}),
    ("Transport", "TR", "medium transport", 12, 1.6, 200, 4, 2.5, 0.6, 0.8, {"RU": 0.5, "IN": 0.3, "FR": 0.2}),
    ("FighterM", "MF", "multirole fighter", 18, 0.9, 150, 3, 2.0, 0.5, 1.0, {"FR": 0.8, "IN": 0.2}),
    ("Trainer", "TN", "jet trainer", 16, 1.2, 120, 2, 1.2, 0.4, 0.5, {"IN": 0.9, "FR": 0.1}),
]
FAMILIES = {   # family: (shape range, scale range in flying hours, failure modes)
    "fuel_system": ((1.4, 1.8), (350, 600), {"pressure_low": 0.5, "leak": 0.3, "contamination": 0.2}),
    "oil_system": ((1.5, 1.9), (380, 650), {"pressure_low": 0.4, "chip_detected": 0.4, "leak": 0.2}),
    "hydraulics": ((1.3, 1.7), (340, 600), {"leak": 0.5, "pressure_low": 0.3, "corrosion": 0.2}),
    "avionics": ((1.1, 1.4), (300, 700), {"bite_fail": 0.7, "intermittent": 0.3}),
    "electrical": ((1.4, 1.8), (380, 600), {"no_output": 0.5, "overheat": 0.3, "intermittent": 0.2}),
    "environmental": ((1.6, 2.0), (400, 600), {"overheat": 0.4, "bearing_wear": 0.4, "erosion": 0.2}),
    "landing_gear": ((1.9, 2.4), (450, 700), {"wear": 0.7, "leak": 0.3}),
    "engine": ((1.4, 1.8), (450, 650), {"flow_error": 0.6, "intermittent": 0.4}),
    "drivetrain": ((1.6, 2.2), (550, 800), {"wear": 0.55, "crack": 0.15, "corrosion": 0.3}),
    "rotor": ((1.8, 2.3), (600, 850), {"wear": 0.6, "leak": 0.4}),
}
APPROVED = {"RU": ("BRD-1", "HAL-K", "OEM-RU"), "FR": ("HAL-K", "OEM-FR"), "IN": ("BRD-1", "HAL-K", "MSME-P")}
DEFAULT_AGENCY = {"RU": ("OEM-RU", "BRD-1"), "FR": ("OEM-FR", "HAL-K"), "IN": ("BRD-1", "HAL-K", "MSME-P")}


def _repair_demand(fleets, pns, agencies) -> dict[str, float]:
    """Units in repair at once, on average, per agency (failures per day x turnaround)."""
    out = {a: 0.0 for a in agencies}
    for f in fleets.values():
        n = sum(f.tails_per_base.values())
        for p in pns.values():
            if p.fleet == f.id:
                out[p.default_agency] += n * p.positions * f.fh_per_day / p.eta * agencies[p.default_agency].tat_median_days
    return out


def make_scaled_world(n_fleets: int = 6, n_bases: int = 12, squadrons_per_fleet: int = 9, pns_per_fleet: int = 25,
                      bases_per_fleet: int = 3, seed: int = 7, rogue_fraction: float = 0.03,
                      rogue_frailty: float = 4.0) -> World:
    rng = np.random.default_rng(seed)
    n_fleets = min(n_fleets, len(TYPES))
    base_ids = [f"B{i + 1}" for i in range(n_bases)]
    stationed: dict[str, list[str]] = {b: [] for b in base_ids}
    fleets, pns = {}, {}
    for k, (fid, prefix, role, sq, fh, insp, insp_d, mttr_f, mttr_s, w, origins) in enumerate(TYPES[:n_fleets]):
        at = [base_ids[(k * bases_per_fleet + j) % n_bases] for j in range(bases_per_fleet)]
        per_base = {b: 0 for b in at}
        for s in range(squadrons_per_fleet):
            per_base[at[s % len(at)]] += sq
        for b in at:
            stationed[b].append(fid)
        fleets[fid] = FleetType(fid, role, sq, fh, insp, insp_d, mttr_f, mttr_s, per_base, role_weight=w)
        fams = [f for f in FAMILIES if not (f in ("drivetrain", "rotor") and not fid.startswith("Helo"))]
        for j in range(pns_per_fleet):
            fam = fams[j % len(fams)]
            (b_lo, b_hi), (e_lo, e_hi), _ = FAMILIES[fam]
            origin = rng.choice(list(origins), p=list(origins.values()))
            pn = f"{prefix}-{fam[:2].upper()}-{j + 1:02d}"
            pns[pn] = PartNumber(pn, f"{fam.replace('_', ' ')} unit {j + 1}", fam, fid, str(origin),
                                 round(float(rng.uniform(b_lo, b_hi)), 2), round(float(rng.uniform(e_lo, e_hi))),
                                 int(rng.choice([1, 1, 1, 2, 2, 4])), APPROVED[str(origin)],
                                 str(rng.choice(DEFAULT_AGENCY[str(origin)])), round(float(rng.uniform(4, 60)), 1),
                                 round(float(rng.uniform(40, 200))))
    bases = {b: Base(b, ENVS[i % len(ENVS)], tuple(stationed[b])) for i, b in enumerate(base_ids)}
    tails = [{"id": f"{TYPES[k][1]}-{b}-{i + 1:02d}", "fleet": f.id, "base": b}
             for k, f in enumerate(fleets.values()) for b, n in f.tails_per_base.items() for i in range(n)]

    # depot capacity: as many repair slots per unit of expected demand as in the default world
    base_ag = default_agencies()
    demand = _repair_demand(fleets, pns, base_ag)
    ref_world = make_world()
    ref_demand = _repair_demand(ref_world.fleets, ref_world.pns, base_ag)
    slots_per_unit = sum(a.servers for a in base_ag.values()) / sum(ref_demand.values())   # the default world's
    agencies = {a.id: Agency(a.id, a.kind, a.country, a.q, a.tat_median_days, a.tat_sigma,
                             max(a.servers, int(math.ceil(slots_per_unit * demand[a.id]))), a.transport_days)
                for a in base_ag.values()}

    serials: list[Serial] = []
    initial_install, initial_tso, initial_stock = {}, {}, {}

    def new_serial(pn: str) -> int:
        serials.append(Serial(len(serials), pn, 1.0, f"{pn}-L{rng.integers(1, 6)}"))
        return len(serials) - 1

    by_fleet = {f: [p for p in pns.values() if p.fleet == f] for f in fleets}
    for t in tails:
        for p in by_fleet[t["fleet"]]:
            for slot in range(p.positions):
                sid = new_serial(p.pn)
                initial_install[(t["id"], p.pn, slot)] = sid
                initial_tso[sid] = float(rng.uniform(0.0, 0.8 * p.eta))
    for f in fleets.values():
        for b, n in f.tails_per_base.items():
            for p in by_fleet[f.id]:
                ag = agencies[p.default_agency]
                pipeline = n * p.positions * f.fh_per_day / p.eta * (ag.tat_median_days + 2 * ag.transport_days)
                initial_stock[(b, p.pn)] = [new_serial(p.pn) for _ in range(max(1, int(round(pipeline))))]
    rogue = set(int(s) for s in rng.choice(len(serials), size=int(round(rogue_fraction * len(serials))), replace=False))
    for s in rogue:
        serials[s].frailty = rogue_frailty
    env_effect = {(fam, env): round(float(rng.uniform(0.5, 0.85)), 2)
                  for fam in FAMILIES for env in ENVS if rng.random() < 0.12}
    return World(seed=seed, fleets=fleets, bases=bases, pns=pns, agencies=agencies, regimes=default_regimes(),
                 env_effect=env_effect, failure_modes={f: dict(v[2]) for f, v in FAMILIES.items()},
                 env_mode_boost={}, tails=tails, serials=serials, initial_install=initial_install,
                 initial_tso_fh=initial_tso, initial_stock=initial_stock, rogue_serials=rogue)


SIZES = {   # name: (fleets, bases, squadrons per fleet, part numbers per fleet, bases per fleet)
    "S": None,                        # the default world: 70 aircraft
    "M": (3, 6, 6, 20, 2),            # ~ 280 aircraft
    "L": (6, 12, 9, 25, 3),           # ~ 900 aircraft
    "XL": (6, 24, 18, 30, 6),         # ~ 1,800 aircraft, an air force's order of size
}


def sized_world(name: str, seed: int = 7) -> World:
    from nirantar.bharat_fleet.world import make_world
    if SIZES[name] is None:
        return make_world(seed=seed)
    f, b, s, p, bf = SIZES[name]
    return make_scaled_world(f, b, s, p, bf, seed=seed)
