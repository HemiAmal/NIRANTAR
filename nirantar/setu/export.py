"""Write a synthetic fleet's records as source-system export files (e-MMS / IMMOLS style).

This makes BHARAT-FLEET just another data source: the rest of NIRANTAR reads
only what SETU imports from these files, exactly as it would read real
exports. Optional defect injection plants known errors so the import checks
can be measured.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from nirantar.bharat_fleet.world import World

EPOCH = datetime(2021, 10, 6)
REMOVE_CODE = {"failure": "FAIL", "preventive": "PREV", "cannibalised": "CANN"}
SOURCE_CODE = {"repair": "REPAIR", "new": "NEW", "transfer": "TRANSFER", "lateral": "LATERAL"}


def serial_id(sid) -> str:
    return f"SN-{int(sid):06d}"


def _t(day: float, epoch: datetime) -> str:
    if day is None or (isinstance(day, float) and np.isnan(day)):
        return ""
    return (epoch + timedelta(days=float(day))).strftime("%Y-%m-%d %H:%M")


def _num(x, nd: int = 2) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{float(x):.{nd}f}"


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def supply_risk(world: World) -> dict:
    """The supplier regime model (levels, delay multipliers, daily transitions) as master data."""
    return {c: {"states": list(m.states), "multipliers": list(m.tat_multiplier),
                "transition": [list(r) for r in m.transition]} for c, m in world.regimes.items()}


def export(world: World, records: dict, snapshot: dict, horizon_day: float, out: str | Path,
           epoch: datetime = EPOCH, defect_rate: float = 0.0, seed: int = 0) -> dict:
    """Write masters, e-MMS and IMMOLS files plus a manifest. Returns the manifest
    (with ``planted``: the rows corrupted on purpose, if any)."""
    out = Path(out)
    rng = np.random.default_rng(seed)

    _write(out / "masters/bases.csv", ["BASE", "ENV_CLASS"], [[b.id, b.env] for b in world.bases.values()])
    _write(out / "masters/fleets.csv",
           ["TYPE", "ROLE", "FH_PER_DAY", "INSP_INTERVAL_FH", "INSP_DAYS", "MTTR_FAIL_DAYS", "MTTR_SWAP_DAYS",
            "ROLE_WEIGHT", "SQN_UE"],
           [[f.id, f.role, f.fh_per_day, f.inspection_interval_fh, f.inspection_days, f.mttr_fail_days,
             f.mttr_swap_days, f.role_weight, f.squadron_ue] for f in world.fleets.values()])
    _write(out / "masters/aircraft.csv", ["TAIL", "TYPE", "BASE"], [[t["id"], t["fleet"], t["base"]] for t in world.tails])
    _write(out / "masters/agencies.csv", ["AGENCY", "KIND", "COUNTRY"],
           [[a.id, a.kind, a.country] for a in world.agencies.values()])
    _write(out / "masters/parts.csv",
           ["PARTNO", "NOMENCLATURE", "SYSTEM", "TYPE", "POSITIONS", "ORIGIN", "APPROVED_AGENCIES", "DEFAULT_AGENCY",
            "UNIT_COST_LAKH", "LEAD_DAYS"],
           [[p.pn, p.name, p.family, p.fleet, p.positions, p.origin, ";".join(p.eligible_agencies), p.default_agency,
             p.unit_cost_lakh, p.procurement_days] for p in world.pns.values()])

    ins = [[serial_id(s["serial"]), s["pn"], s["tail"], s.get("position", 1), _t(s["install_day"], epoch),
            _num(s["entry_fh"]), _t(s["removal_day"], epoch),
            _num(s["exit_fh"]) if s.get("removal_reason") else "", REMOVE_CODE.get(s.get("removal_reason"), ""),
            "" if s.get("removal_reason") else _num(s["exit_fh"])]
           for s in records["spells"]]
    planted = []
    if defect_rate > 0:
        ins, planted = _plant(ins, defect_rate, rng)
    _write(out / "emms/installs.csv", ["SERIALNUM", "ITEMNUM", "ASSETNUM", "POSITION", "INSTALLDATE", "INSTALL_TSR",
                                       "REMOVEDATE", "REMOVE_TSR", "REMOVECODE", "CURRENT_TSR"], ins)
    ro = []
    for i, r in enumerate(records["repairs"]):
        wt = "DEEP" if r.get("deep_strip") else "OH" if r.get("overhaul") else "REP"
        ro.append([f"WO{i + 1:07d}", serial_id(r["serial"]), r["pn"], r["agency"], r["from_base"],
                   _t(r["sent_day"], epoch), _t(r["start_day"], epoch), _t(r["done_day"], epoch), wt,
                   _num(r.get("fh_since_repair"))])
    _write(out / "emms/repair_orders.csv", ["WONUM", "SERIALNUM", "ITEMNUM", "VENDOR", "FROMSITE", "SENTDATE",
                                            "ACTSTART", "ACTFINISH", "WORKTYPE", "TSR"], ro)
    _write(out / "emms/defects.csv", ["TICKETID", "REPORTDATE", "ASSETNUM", "ITEMNUM", "SERIALNUM", "PROBLEMCODE",
                                      "DESCRIPTION"],
           [[f"DF{i + 1:07d}", _t(s["day"], epoch), s["tail"], s["pn"], serial_id(s["serial"]), s["mode"].upper(),
             s["text"]] for i, s in enumerate(records["snags"])])
    _write(out / "immols/receipts.csv", ["RECEIPTDATE", "DEPOT", "PARTNO", "SERIALNO", "SOURCE"],
           [[_t(r["day"], epoch), r["base"], r["pn"], serial_id(r["serial"]), SOURCE_CODE.get(r["source"], "NEW")]
            for r in records.get("receipts", [])])
    as_of = _t(horizon_day, epoch)
    pn_of = {**{s.id: s.pn for s in world.serials}, **{int(k): v for k, v in snapshot.get("new_pn", {}).items()}}
    _write(out / "immols/onhand.csv", ["ASOFDATE", "DEPOT", "PARTNO", "SERIALNO"],
           [[as_of, base, pn, serial_id(sid)] for (base, pn), sids in snapshot["stock"].items() for sid in sids
            if pn_of.get(int(sid), pn) == pn])
    (out / "masters/supply_risk.json").write_text(json.dumps(supply_risk(world), indent=1), encoding="utf-8")
    manifest = {"generator": "BHARAT-FLEET (synthetic)", "epoch": _t(0.0, epoch), "as_of": as_of,
                "files": sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*.csv")),
                "planted_defects": planted}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _plant(rows: list[list], rate: float, rng) -> tuple[list[list], list[dict]]:
    """Corrupt a share of install rows with known defects (row numbers are 1-based data rows)."""
    rows = [list(r) for r in rows]
    n = len(rows)
    k = max(1, int(rate * n))
    planted = []
    kinds = ["UNKNOWN_PART", "BAD_TIME", "REMOVAL_BEFORE_INSTALL", "BAD_POSITION", "DUPLICATE"]
    for i, kind in zip(rng.choice(n, size=k, replace=False), rng.choice(kinds, size=k)):
        r = rows[int(i)]
        if kind == "UNKNOWN_PART":
            r[1] = "XX-" + r[1]
        elif kind == "BAD_TIME":
            r[4] = r[4].replace("-", "/", 1) + "Z"
        elif kind == "REMOVAL_BEFORE_INSTALL":
            if not r[6]:
                continue
            r[6], r[4] = r[4], r[6]
        elif kind == "BAD_POSITION":
            r[3] = 9
        elif kind == "DUPLICATE":
            rows.append(list(r))
            planted.append({"row": len(rows), "kind": str(kind)})
            continue
        planted.append({"row": int(i) + 1, "kind": str(kind)})
    return rows, planted
