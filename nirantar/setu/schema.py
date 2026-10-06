"""SETU record store: the canonical maintenance-and-supply schema in SQLite.

Everything downstream (reliability fits, agency scorecards, signals, the fleet
state, the decision desk) reads from here, never from a simulator. SQLite keeps
it to one file and the Python standard library, which suits an air-gapped node;
the SQL is plain enough to move to PostgreSQL for a multi-user deployment.

Times are stored as ISO text (``YYYY-MM-DD HH:MM``); ``Store.frames()`` returns
them as fractional days since the store's epoch, the unit the models use.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = 1
TIME_FMT = "%Y-%m-%d %H:%M"

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS bases (base TEXT PRIMARY KEY, env TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fleets (
  fleet TEXT PRIMARY KEY, role TEXT, fh_per_day REAL NOT NULL, inspection_interval_fh REAL NOT NULL,
  inspection_days REAL NOT NULL, mttr_fail_days REAL NOT NULL, mttr_swap_days REAL NOT NULL,
  role_weight REAL NOT NULL, squadron_ue INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS aircraft (
  tail TEXT PRIMARY KEY, fleet TEXT NOT NULL REFERENCES fleets(fleet), base TEXT NOT NULL REFERENCES bases(base));
CREATE TABLE IF NOT EXISTS agencies (agency TEXT PRIMARY KEY, kind TEXT, country TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parts (
  pn TEXT PRIMARY KEY, name TEXT NOT NULL, family TEXT NOT NULL, fleet TEXT NOT NULL REFERENCES fleets(fleet),
  positions INTEGER NOT NULL, origin TEXT NOT NULL, eligible_agencies TEXT NOT NULL, default_agency TEXT NOT NULL,
  unit_cost_lakh REAL NOT NULL, procurement_days REAL NOT NULL);

CREATE TABLE IF NOT EXISTS installs (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, serial TEXT NOT NULL, pn TEXT NOT NULL, tail TEXT NOT NULL,
  position INTEGER NOT NULL, install_time TEXT NOT NULL, install_hours REAL NOT NULL,
  removal_time TEXT, removal_hours REAL, removal_reason TEXT, current_hours REAL);
CREATE TABLE IF NOT EXISTS repair_orders (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, order_no TEXT, serial TEXT NOT NULL, pn TEXT NOT NULL,
  agency TEXT NOT NULL, from_base TEXT NOT NULL, sent_time TEXT NOT NULL, start_time TEXT, done_time TEXT,
  work_type TEXT NOT NULL, hours_at_induction REAL);
CREATE TABLE IF NOT EXISTS defects (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, ticket TEXT, report_time TEXT NOT NULL, tail TEXT NOT NULL,
  pn TEXT NOT NULL, serial TEXT, problem_code TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS receipts (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, receipt_time TEXT NOT NULL, base TEXT NOT NULL,
  pn TEXT NOT NULL, serial TEXT NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS onhand (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, as_of TEXT NOT NULL, base TEXT NOT NULL,
  pn TEXT NOT NULL, serial TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS ingest_batches (
  batch INTEGER PRIMARY KEY, source TEXT NOT NULL, file TEXT NOT NULL, sha256 TEXT NOT NULL, at TEXT NOT NULL,
  rows INTEGER NOT NULL, accepted INTEGER NOT NULL, quarantined INTEGER NOT NULL, ledger_seq INTEGER);
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY, batch INTEGER NOT NULL, row_no INTEGER NOT NULL, target TEXT NOT NULL,
  issue TEXT NOT NULL, detail TEXT, raw TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS data_issues (
  id INTEGER PRIMARY KEY, target TEXT NOT NULL, record_id INTEGER NOT NULL, issue TEXT NOT NULL,
  serial TEXT, pn TEXT, found_at TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0);

CREATE INDEX IF NOT EXISTS ix_installs_serial ON installs(serial);
CREATE INDEX IF NOT EXISTS ix_installs_tail ON installs(tail);
CREATE INDEX IF NOT EXISTS ix_repairs_serial ON repair_orders(serial);
"""

MASTER_TABLES = ("bases", "fleets", "aircraft", "agencies", "parts")
EVENT_TABLES = ("installs", "repair_orders", "defects", "receipts", "onhand")


def to_time(dt: datetime) -> str:
    return dt.strftime(TIME_FMT)


class Store:
    """One SQLite file holding the canonical records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(DDL)
        if self.meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))

    # -- meta ----------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        row = self.con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.tx():
            self.con.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                             (key, value, value))

    @property
    def epoch(self) -> datetime:
        e = self.meta("epoch")
        if e is None:
            raise ValueError("the store has no epoch yet: import a source with a manifest first")
        return datetime.strptime(e, TIME_FMT)

    @property
    def as_of(self) -> datetime | None:
        a = self.meta("as_of")
        return datetime.strptime(a, TIME_FMT) if a else None

    @contextmanager
    def tx(self):
        try:
            yield self.con
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    def close(self) -> None:
        self.con.close()

    # -- reading -------------------------------------------------------------
    def table(self, name: str) -> pd.DataFrame:
        if name not in MASTER_TABLES + EVENT_TABLES + ("ingest_batches", "quarantine", "data_issues"):
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name}", self.con)

    def counts(self) -> dict[str, int]:
        return {t: self.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in MASTER_TABLES + EVENT_TABLES + ("quarantine", "data_issues")}

    def day(self, s: pd.Series) -> pd.Series:
        """ISO times -> fractional days since the epoch (NaN stays NaN)."""
        t = pd.to_datetime(s, format=TIME_FMT, errors="coerce")
        return (t - pd.Timestamp(self.epoch)) / pd.Timedelta(days=1)

    def frames(self) -> dict[str, pd.DataFrame]:
        """Model-ready tables in day units, with the column names the analytics use."""
        a = self.table("aircraft")
        bases = self.table("bases").set_index("base")["env"]
        fleet_of, base_of = a.set_index("tail")["fleet"], a.set_index("tail")["base"]
        ins = self.table("installs")
        spells = pd.DataFrame({
            "serial": ins["serial"], "pn": ins["pn"], "tail": ins["tail"], "fleet": ins["tail"].map(fleet_of),
            "base": ins["tail"].map(base_of), "env": ins["tail"].map(base_of).map(bases),
            "install_day": self.day(ins["install_time"]), "entry_fh": ins["install_hours"],
            "removal_day": self.day(ins["removal_time"]),
            "exit_fh": ins["removal_hours"].where(ins["removal_time"].notna(), ins["current_hours"]),
            "removal_reason": ins["removal_reason"], "position": ins["position"], "record_id": ins["id"]})
        # previous agency and number of prior repairs, from the repair orders before each installation
        ro = self.table("repair_orders")
        rep = pd.DataFrame({
            "serial": ro["serial"], "pn": ro["pn"], "agency": ro["agency"], "from_base": ro["from_base"],
            "sent_day": self.day(ro["sent_time"]), "start_day": self.day(ro["start_time"]),
            "done_day": self.day(ro["done_time"]), "work_type": ro["work_type"],
            "overhaul": ro["work_type"].isin(["OVERHAUL", "DEEP"]), "deep_strip": ro["work_type"] == "DEEP",
            "fh_since_repair": ro["hours_at_induction"], "record_id": ro["id"]})
        spells = _attach_prior_repairs(spells, rep)
        d = self.table("defects")
        snags = pd.DataFrame({"day": self.day(d["report_time"]), "tail": d["tail"], "pn": d["pn"],
                              "serial": d["serial"], "mode": d["problem_code"], "text": d["description"],
                              "fleet": d["tail"].map(fleet_of), "base": d["tail"].map(base_of),
                              "env": d["tail"].map(base_of).map(bases)})
        parts = self.table("parts").set_index("pn")
        snags["family"] = snags["pn"].map(parts["family"]) if len(parts) else None
        r = self.table("receipts")
        receipts = pd.DataFrame({"day": self.day(r["receipt_time"]), "base": r["base"], "pn": r["pn"],
                                 "serial": r["serial"], "source": r["source"]})
        o = self.table("onhand")
        onhand = pd.DataFrame({"day": self.day(o["as_of"]), "base": o["base"], "pn": o["pn"], "serial": o["serial"]})
        return {"spells": spells, "repairs": rep, "snags": snags, "receipts": receipts, "onhand": onhand}

    def masters(self) -> dict[str, pd.DataFrame]:
        out = {t: self.table(t) for t in MASTER_TABLES}
        out["parts"]["eligible_agencies"] = out["parts"]["eligible_agencies"].map(json.loads)
        return out

    def now_day(self) -> float:
        """The 'as of' time of the latest import, in days since the epoch."""
        a = self.as_of
        return (a - self.epoch) / timedelta(days=1) if a else float("nan")


def _attach_prior_repairs(spells: pd.DataFrame, rep: pd.DataFrame) -> pd.DataFrame:
    if spells.empty:
        spells["prev_agency"], spells["n_prior_repairs"] = [], []
        return spells
    done = rep.dropna(subset=["done_day"]).sort_values("done_day")
    prev, n_prior = [], []
    by_serial = {s: g for s, g in done.groupby("serial")}
    for s, t in zip(spells["serial"], spells["install_day"]):
        g = by_serial.get(s)
        if g is None:
            prev.append("UNKNOWN"); n_prior.append(0); continue
        before = g[g["done_day"] <= t + 1e-6]
        if before.empty:
            prev.append("UNKNOWN"); n_prior.append(0); continue
        last = before.iloc[-1]
        prev.append(last["agency"] + ("#OH" if bool(last["overhaul"]) else ""))
        n_prior.append(len(before))
    spells = spells.copy()
    spells["prev_agency"], spells["n_prior_repairs"] = prev, n_prior
    return spells
