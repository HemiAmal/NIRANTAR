"""How NIRANTAR's stages grow with fleet size (``python -m nirantar scale-bench --size L``).

Sizes (``bharat_fleet/scale.py``): S is the 70-aircraft default world; M ~290, L ~850 and XL ~1,700 aircraft
(the order of an air force's fleet), with 60 to 180 part numbers and 14k to 107k installed units.
Every stage of the records-to-decision path is timed on one machine:

history (5 simulated years) -> reliability fit (with uncertainty) -> export as e-MMS/IMMOLS files -> checked
import into the record store -> estimate of the world and today's state from records -> today's plan
(priced on the fleet's futures) -> ledger signing and verification at that volume.
"""
from __future__ import annotations

import os
import resource
import tempfile
import time
from pathlib import Path


def _rss_mb() -> int:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(r / 1024) if os.uname().sysname != "Darwin" else int(r / 1024 / 1024)


def run(size: str = "M", plan: bool = True, workers: int | None = None, log=print) -> dict:
    from nirantar.bharat_fleet.scale import sized_world
    from nirantar.chanakya.desk import build_plan
    from nirantar.chitragupta.ledger import Ledger, Signer
    from nirantar.dhanvantari.tier_c import fit_tier_c
    from nirantar.records import to_frames
    from nirantar.sanjaya.ensemble import P0
    from nirantar.sanjaya.twin import Twin
    from nirantar.setu.estimate import estimate
    from nirantar.setu.export import export
    from nirantar.setu.ingest import Importer
    from nirantar.setu.schema import Store

    out: dict = {"size": size, "cpus": os.cpu_count(), "workers": workers, "stages": {}}

    def stage(name, fn):
        t = time.time()
        v = fn()
        out["stages"][name] = round(time.time() - t, 1)
        log(f"  {name}: {out['stages'][name]} s")
        return v

    w = stage("world", lambda: sized_world(size))
    out["fleet"] = {"aircraft": len(w.tails), "types": len(w.fleets), "bases": len(w.bases), "part_numbers": len(w.pns),
                    "units": len(w.serials)}
    h = stage("history_5_years", lambda: Twin(w, P0, 1825, seed=99, record=True).run())
    fr = stage("frames", lambda: to_frames(h.records))
    out["records"] = {k: len(v) for k, v in fr.items()}
    fam = {p: v.family for p, v in w.pns.items()}
    m = stage("reliability_fit", lambda: fit_tier_c(fr["spells"], fam))
    with tempfile.TemporaryDirectory() as d:
        stage("export_files", lambda: export(w, h.records, h.snapshot, 1825, Path(d) / "x"))
        st = Store(Path(d) / "s.db")
        stage("import_checked", lambda: Importer(st).import_folder(Path(d) / "x"))
        e = stage("estimate_from_records", lambda: estimate(st))
        st.close()
    out["estimate_rogues"] = len(e.world.rogue_serials)
    if plan:
        p = stage("plan_today", lambda: build_plan(e.world, e.start, e.model, P0, dict(e.model.n_failures_by_pn),
                                                   e.dq, workers=workers))
        out["plan"] = {"candidates": p["n_candidates"], "refined": p["n_refined"], "actions": len(p["items"]),
                       "value_wAAD": (p["joint"] or {}).get("mrv"), "ci95": (p["joint"] or {}).get("ci95"),
                       "priced_by_fleet": p.get("priced_by_fleet")}
    with tempfile.TemporaryDirectory() as d:
        L, s = Ledger(Path(d) / "l.jsonl"), Signer.generate("bench")
        n = 20_000
        stage(f"ledger_append_{n}", lambda: [L.append("t", {"i": i}, s) for i in range(n)])
        stage(f"ledger_verify_{n}", lambda: Ledger(Path(d) / "l.jsonl").verify_all())
    out["peak_memory_mb"] = _rss_mb()
    return out
