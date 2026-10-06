"""Real public reliability datasets, as the installation spells DHANVANTARI fits.

Each loader returns ``(spells, family_of)`` in the same shape as records coming
out of the SETU store: one row per period a unit was in service, with the age
at entry and exit, whether it ended in a failure, and which agency (if any)
repaired it before. Nothing here is tuned to the data; the fits that follow use
the same code and priors as for fleet records.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "datasets"
COLUMNS = ["serial", "pn", "env", "install_day", "entry_fh", "exit_fh", "removal_reason", "prev_agency"]


def _spells(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def genfan() -> tuple[pd.DataFrame, dict]:
    """70 diesel-generator fans, one service period each (hours)."""
    d = pd.read_csv(DATA / "genfan.csv")
    rows = [{"serial": f"FAN{i:02d}", "pn": "GEN-FAN", "env": "field", "install_day": 0.0, "entry_fh": 0.0,
             "exit_fh": float(r.hours), "removal_reason": "failure" if r.status == 1 else None,
             "prev_agency": "UNKNOWN"} for i, r in enumerate(d.itertuples())]
    return _spells(rows), {"GEN-FAN": "fan"}


def valve_seats(jitter: float = 0.5) -> pd.DataFrame:
    """Replacement history per engine: (engine, day, replaced) with tied replacements spread by ``jitter`` days."""
    d = pd.read_csv(DATA / "valve_seats.csv").sort_values(["id", "time", "status"], ascending=[True, True, False])
    out = []
    for eng, g in d.groupby("id"):
        last = -1.0
        for r in g.itertuples():
            t = float(r.time)
            if r.status == 1 and t <= last:
                t = last + jitter
            out.append((int(eng), t, int(r.status)))
            if r.status == 1:
                last = t
    return pd.DataFrame(out, columns=["engine", "day", "replaced"])


def valve_seat_spells(hist: pd.DataFrame, cutoff: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Spells between replacements (age since last replacement), repaired in place by the engine shop.

    The shop's repair effectiveness q is estimated like any repair agency's: q = 1 means the engine
    keeps ageing after a seat is replaced (minimal repair), q = 0 means as good as new."""
    rows = []
    for eng, g in hist.groupby("engine"):
        end = float(g["day"].max()) if cutoff is None else min(float(g["day"].max()), cutoff)
        prev, n = 0.0, 0
        for r in g.itertuples():
            if r.replaced != 1 or r.day > end:
                continue
            rows.append({"serial": f"E{eng}", "pn": "VALVE-SEAT", "env": "field", "install_day": prev,
                         "entry_fh": 0.0, "exit_fh": r.day - prev, "removal_reason": "failure",
                         "prev_agency": "SHOP" if n else "UNKNOWN"})
            prev, n = r.day, n + 1
        if end > prev:
            rows.append({"serial": f"E{eng}", "pn": "VALVE-SEAT", "env": "field", "install_day": prev,
                         "entry_fh": 0.0, "exit_fh": end - prev, "removal_reason": None,
                         "prev_agency": "SHOP" if n else "UNKNOWN"})
    return _spells(rows), {"VALVE-SEAT": "valve_seat"}


def braking_grids() -> tuple[pd.DataFrame, dict]:
    """Braking grids on locomotives, two manufacturing batches as two part numbers; a new grid is fitted
    at each replacement (renewal), and the locomotive is the unit that may run hard on its grids."""
    d = pd.read_csv(DATA / "braking_grids.csv")
    rows = [{"serial": f"L{r.locomotive}", "pn": f"GRID-BATCH{r.batch}", "env": "field", "install_day": float(r.day1),
             "entry_fh": 0.0, "exit_fh": float(r.day2 - r.day1), "removal_reason": "failure" if r.status == 1 else None,
             "prev_agency": "UNKNOWN"} for r in d.itertuples()]
    return _spells(rows), {"GRID-BATCH1": "braking_grid", "GRID-BATCH2": "braking_grid"}


def maker(model: str) -> str:
    head = model.split()[0]
    return "Seagate" if head.startswith("ST") else head.upper() if head.upper() in ("HGST", "WDC", "TOSHIBA") \
        else "Hitachi" if head == "Hitachi" else head


TEMP_BANDS = ((0, 25, "below 25C"), (25, 30, "25-30C"), (30, 99, "30C and above"))


def drives() -> pd.DataFrame:
    d = pd.read_csv(DATA / "backblaze_drives.csv.gz")
    d["maker"] = d["model"].map(maker)
    d["env"] = pd.cut(d["temp"], [b[0] for b in TEMP_BANDS] + [TEMP_BANDS[-1][1]], right=False,
                      labels=[b[2] for b in TEMP_BANDS]).astype(str)
    return d


def drive_spells(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One service period per drive (days); model = part number, maker = family, temperature band = environment."""
    sp = pd.DataFrame({"serial": d["serial"].to_numpy(), "pn": d["model"].to_numpy(), "env": d["env"].to_numpy(),
                       "install_day": 0.0, "entry_fh": 0.0, "exit_fh": d["time"].to_numpy(float),
                       "removal_reason": np.where(d["status"].to_numpy() == 1, "failure", None),
                       "prev_agency": "UNKNOWN"})
    return sp, dict(zip(d["model"], d["maker"]))
