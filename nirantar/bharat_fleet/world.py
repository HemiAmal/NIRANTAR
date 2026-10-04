"""BHARAT-FLEET: synthetic national sustainment-enterprise generator.

A *world* holds the hidden ground truth (Weibull lives, environment effects,
agency repair quality, rogue serials, supply regimes). The digital twin
(``nirantar.sanjaya``) simulates operations on top of it, and the analytics
modules must recover the truth from the records the twin emits.

Everything here is synthetic. Structures are loosely inspired by public
descriptions of Indian fleets; no parameter is real IAF data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

ENVIRONMENTS = ("coastal_saline", "desert_dust", "high_altitude", "humid_ne")


@dataclass(frozen=True)
class PartNumber:
    pn: str
    name: str
    family: str
    fleet: str
    origin: str               # "RU", "FR", "IN" -> supply country
    beta: float               # true Weibull shape
    eta: float                # true Weibull scale (flight hours)
    positions: int            # installed positions per tail
    eligible_agencies: tuple[str, ...]
    default_agency: str
    unit_cost_lakh: float     # cost of buying one new unit (lakh INR)
    procurement_days: float   # median lead time for a new unit


@dataclass(frozen=True)
class Agency:
    id: str
    kind: str                 # BRD / HAL / MSME / OEM
    country: str              # supply country for regime effects ("IN" = domestic)
    q: float                  # true Kijima repair-effectiveness (0 = as new)
    tat_median_days: float
    tat_sigma: float          # log-normal sigma of TAT
    servers: int              # parallel repair slots
    transport_days: float     # one-way shipping time to/from bases


@dataclass(frozen=True)
class Base:
    id: str
    env: str
    fleets: tuple[str, ...]


@dataclass(frozen=True)
class FleetType:
    id: str
    role: str
    squadron_ue: int
    fh_per_day: float
    inspection_interval_fh: float
    inspection_days: float
    mttr_fail_days: float     # hands-on time after an in-service failure
    mttr_swap_days: float     # hands-on time to install a waiting spare
    tails_per_base: dict[str, int]
    role_weight: float = 1.0  # value of one aircraft-available-day of this type (wAAD)


@dataclass(frozen=True)
class RegimeModel:
    """Daily Markov chain over supply regimes for one supplier country."""
    country: str
    states: tuple[str, ...]
    tat_multiplier: tuple[float, ...]   # multiplies shipping/customs/payment delay
    transition: tuple[tuple[float, ...], ...]


@dataclass
class Serial:
    id: int
    pn: str
    frailty: float            # >1 means it fails faster (rogue if large)
    lot: str


@dataclass
class World:
    seed: int
    fleets: dict[str, FleetType]
    bases: dict[str, Base]
    pns: dict[str, PartNumber]
    agencies: dict[str, Agency]
    regimes: dict[str, RegimeModel]
    env_effect: dict[tuple[str, str], float]          # (family, env) -> eta multiplier
    failure_modes: dict[str, dict[str, float]]        # family -> mode -> prob
    env_mode_boost: dict[tuple[str, str], str]        # (family, env) -> boosted mode
    tails: list[dict]                                  # {id, fleet, base}
    serials: list[Serial]
    initial_install: dict[tuple[str, str, int], int]   # (tail, pn, slot) -> serial id
    initial_tso_fh: dict[int, float]                   # serial -> time since overhaul
    initial_stock: dict[tuple[str, str], list[int]]    # (base, pn) -> serial ids
    rogue_serials: set[int] = field(default_factory=set)

    def eta_true(self, pn: str, env: str) -> float:
        p = self.pns[pn]
        return p.eta * self.env_effect.get((p.family, env), 1.0)

    def base_env(self, base_id: str) -> str:
        return self.bases[base_id].env

    def tails_of(self, fleet: str) -> list[dict]:
        return [t for t in self.tails if t["fleet"] == fleet]


def _fighter_pns() -> list[PartNumber]:
    ru_ag = ("BRD-1", "HAL-K", "OEM-RU")
    in_ag = ("BRD-1", "HAL-K", "MSME-P")
    return [
        PartNumber("FH-FP-01", "Engine fuel pump", "fuel_system", "FighterH", "RU", 1.6, 380, 2, ru_ag, "OEM-RU", 18, 150),
        PartNumber("FH-OP-02", "Engine oil pump", "oil_system", "FighterH", "RU", 1.8, 420, 2, ru_ag, "BRD-1", 12, 140),
        PartNumber("FH-HP-03", "Hydraulic pump", "hydraulics", "FighterH", "RU", 1.5, 360, 2, ru_ag, "BRD-1", 15, 160),
        PartNumber("FH-AC-04", "Flight-control actuator", "hydraulics", "FighterH", "IN", 1.4, 520, 1, in_ag, "MSME-P", 20, 90),
        PartNumber("FH-RD-05", "Radar transmitter", "avionics", "FighterH", "RU", 1.2, 330, 1, ru_ag, "OEM-RU", 60, 200),
        PartNumber("FH-MF-06", "Multi-function display", "avionics", "FighterH", "IN", 1.3, 600, 1, in_ag, "MSME-P", 9, 60),
        PartNumber("FH-GN-07", "AC generator", "electrical", "FighterH", "RU", 1.7, 400, 2, ru_ag, "OEM-RU", 14, 150),
        PartNumber("FH-CT-08", "ECS cooling turbine", "environmental", "FighterH", "RU", 1.9, 450, 1, ru_ag, "BRD-1", 16, 170),
        PartNumber("FH-BR-09", "Wheel brake unit", "landing_gear", "FighterH", "IN", 2.2, 500, 2, in_ag, "MSME-P", 6, 45),
    ]


def _helo_pns() -> list[PartNumber]:
    fr_ag = ("HAL-K", "OEM-FR")
    in_ag = ("BRD-1", "HAL-K", "MSME-P")
    return [
        PartNumber("HU-SW-01", "Swashplate assembly", "drivetrain", "HeloU", "IN", 2.0, 700, 1, in_ag, "HAL-K", 25, 120),
        PartNumber("HU-GB-02", "Accessory gearbox", "drivetrain", "HeloU", "IN", 1.7, 600, 1, in_ag, "HAL-K", 22, 120),
        PartNumber("HU-FC-03", "Fuel control unit", "engine", "HeloU", "FR", 1.5, 520, 2, fr_ag, "OEM-FR", 18, 130),
        PartNumber("HU-HP-04", "Hydraulic pump", "hydraulics", "HeloU", "IN", 1.5, 480, 2, in_ag, "MSME-P", 10, 60),
        PartNumber("HU-AV-05", "Autopilot computer", "avionics", "HeloU", "IN", 1.2, 650, 1, in_ag, "BRD-1", 14, 90),
        PartNumber("HU-ST-06", "Starter-generator", "electrical", "HeloU", "FR", 1.6, 500, 2, fr_ag, "OEM-FR", 12, 120),
        PartNumber("HU-DA-07", "Lead-lag damper", "rotor", "HeloU", "IN", 2.1, 750, 4, in_ag, "MSME-P", 5, 40),
    ]


def default_agencies() -> dict[str, Agency]:
    ags = [
        Agency("BRD-1", "BRD", "IN", 0.25, 32, 0.35, 28, 3),
        Agency("HAL-K", "HAL", "IN", 0.15, 45, 0.30, 26, 3),
        Agency("MSME-P", "MSME", "IN", 0.60, 16, 0.30, 12, 3),
        Agency("OEM-RU", "OEM", "RU", 0.05, 70, 0.40, 50, 12),
        Agency("OEM-FR", "OEM", "FR", 0.05, 60, 0.30, 30, 10),
    ]
    return {a.id: a for a in ags}


def default_regimes() -> dict[str, RegimeModel]:
    return {
        "RU": RegimeModel(
            "RU", ("normal", "stressed", "disrupted"), (1.0, 3.0, 8.0),
            ((0.985, 0.013, 0.002), (0.02, 0.97, 0.01), (0.005, 0.015, 0.98)),
        ),
        "FR": RegimeModel(
            "FR", ("normal", "stressed", "disrupted"), (1.0, 2.0, 4.0),
            ((0.995, 0.004, 0.001), (0.03, 0.965, 0.005), (0.01, 0.02, 0.97)),
        ),
        "IN": RegimeModel("IN", ("normal",), (1.0,), ((1.0,),)),
    }


def make_world(
    seed: int = 7,
    fighter_tails_per_base: int = 20,
    helo_tails_per_base: int = 10,
    rogue_fraction: float = 0.03,
    rogue_frailty: float = 4.0,
    spare_factor: float = 1.0,
) -> World:
    """Build the default two-fleet, four-base BHARAT-FLEET world."""
    rng = np.random.default_rng(seed)
    bases = {
        "B1": Base("B1", "coastal_saline", ("FighterH", "HeloU")),
        "B2": Base("B2", "desert_dust", ("FighterH",)),
        "B3": Base("B3", "high_altitude", ("HeloU",)),
        "B4": Base("B4", "humid_ne", ("HeloU",)),
    }
    fleets = {
        "FighterH": FleetType("FighterH", "heavy fighter", 18, 0.9, 150, 3, 2.0, 0.5,
                              {"B1": fighter_tails_per_base, "B2": fighter_tails_per_base}, role_weight=1.0),
        "HeloU": FleetType("HeloU", "utility helicopter", 12, 0.8, 120, 2, 1.5, 0.5,
                           {"B1": helo_tails_per_base, "B3": helo_tails_per_base, "B4": helo_tails_per_base},
                           role_weight=0.7),
    }
    pns = {p.pn: p for p in _fighter_pns() + _helo_pns()}
    env_effect = {
        ("environmental", "desert_dust"): 0.55,
        ("drivetrain", "coastal_saline"): 0.45,
        ("rotor", "high_altitude"): 0.6,
        ("hydraulics", "humid_ne"): 0.75,
        ("fuel_system", "desert_dust"): 0.8,
    }
    failure_modes = {
        "fuel_system": {"pressure_low": 0.5, "leak": 0.3, "contamination": 0.2},
        "oil_system": {"pressure_low": 0.4, "chip_detected": 0.4, "leak": 0.2},
        "hydraulics": {"leak": 0.5, "pressure_low": 0.3, "corrosion": 0.2},
        "avionics": {"bite_fail": 0.7, "intermittent": 0.3},
        "electrical": {"no_output": 0.5, "overheat": 0.3, "intermittent": 0.2},
        "environmental": {"overheat": 0.4, "bearing_wear": 0.4, "erosion": 0.2},
        "landing_gear": {"wear": 0.7, "leak": 0.3},
        "drivetrain": {"wear": 0.55, "crack": 0.15, "corrosion": 0.3},
        "engine": {"flow_error": 0.6, "intermittent": 0.4},
        "rotor": {"wear": 0.6, "leak": 0.4},
    }
    env_mode_boost = {
        ("drivetrain", "coastal_saline"): "corrosion",
        ("environmental", "desert_dust"): "erosion",
        ("rotor", "high_altitude"): "wear",
        ("hydraulics", "humid_ne"): "corrosion",
    }

    tails: list[dict] = []
    for f in fleets.values():
        for base_id, n in f.tails_per_base.items():
            for i in range(n):
                tails.append({"id": f"{f.id[:2].upper()}-{base_id}-{i + 1:02d}", "fleet": f.id, "base": base_id})

    serials: list[Serial] = []
    initial_install: dict[tuple[str, str, int], int] = {}
    initial_tso: dict[int, float] = {}
    initial_stock: dict[tuple[str, str], list[int]] = {}

    def new_serial(pn: str) -> int:
        sid = len(serials)
        lot = f"{pn}-L{rng.integers(1, 6)}"
        serials.append(Serial(sid, pn, 1.0, lot))
        return sid

    for t in tails:
        for p in pns.values():
            if p.fleet != t["fleet"]:
                continue
            for slot in range(p.positions):
                sid = new_serial(p.pn)
                initial_install[(t["id"], p.pn, slot)] = sid
                # time since overhaul: spread over roughly one mean life
                initial_tso[sid] = float(rng.uniform(0.0, 0.8 * p.eta))

    # Rotable spares at each base, sized from expected pipeline demand.
    for f in fleets.values():
        for base_id, n_tails in f.tails_per_base.items():
            for p in pns.values():
                if p.fleet != f.id:
                    continue
                installed = n_tails * p.positions
                daily_demand = installed * f.fh_per_day / p.eta
                ag = default_agencies()[p.default_agency]
                pipeline = daily_demand * (ag.tat_median_days + 2 * ag.transport_days)
                n_spare = max(1, int(round(spare_factor * pipeline)))
                initial_stock[(base_id, p.pn)] = [new_serial(p.pn) for _ in range(n_spare)]

    rogue: set[int] = set()
    n_rogue = int(round(rogue_fraction * len(serials)))
    for sid in rng.choice(len(serials), size=n_rogue, replace=False):
        serials[int(sid)].frailty = rogue_frailty
        rogue.add(int(sid))

    return World(
        seed=seed, fleets=fleets, bases=bases, pns=pns, agencies=default_agencies(),
        regimes=default_regimes(), env_effect=env_effect, failure_modes=failure_modes,
        env_mode_boost=env_mode_boost, tails=tails, serials=serials,
        initial_install=initial_install, initial_tso_fh=initial_tso, initial_stock=initial_stock,
        rogue_serials=rogue,
    )
