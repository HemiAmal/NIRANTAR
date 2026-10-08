"""SETU import: source exports -> checked, canonical records in the store.

Each file goes through its mapping (column names, time format, code lists),
then every row is checked before it is loaded:

* required fields present, numbers and times parse;
* references exist (part number, aircraft, base, repair agency);
* physics holds (position within the part's positions, removal after
  installation, hours never go backwards, repair dates in order);
* exact duplicates.

A failing row is quarantined with its reason and the raw text, so a data
steward can fix it at source; it never reaches the models. After loading, the
cross-record checks (SATYA: one serial on two aircraft, flying while at a
repair agency, ...) run on the whole store and are listed as data issues.
Each file is one batch, identified by its SHA-256: importing the same file
twice does nothing, and each batch can be signed into the evidence ledger.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nirantar.satya.quality import check_spells
from nirantar.setu.schema import EVENT_TABLES, MASTER_TABLES, TIME_FMT, Store

DEFAULT_MAPPING = Path(__file__).parent / "mappings" / "default.json"
_CANONICAL = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

REQUIRED = {
    "bases": ("base", "env"),
    "fleets": ("fleet", "fh_per_day", "inspection_interval_fh", "inspection_days", "mttr_fail_days", "mttr_swap_days",
               "role_weight", "squadron_ue"),
    "aircraft": ("tail", "fleet", "base"),
    "agencies": ("agency", "country"),
    "parts": ("pn", "name", "family", "fleet", "positions", "origin", "eligible_agencies", "default_agency",
              "unit_cost_lakh", "procurement_days"),
    "installs": ("serial", "pn", "tail", "position", "install_time", "install_hours"),
    "repair_orders": ("serial", "pn", "agency", "from_base", "sent_time", "work_type"),
    "defects": ("report_time", "tail", "pn"),
    "receipts": ("receipt_time", "base", "pn", "serial"),
    "onhand": ("as_of", "base", "pn", "serial"),
}
NUMBERS = {"fh_per_day", "inspection_interval_fh", "inspection_days", "mttr_fail_days", "mttr_swap_days", "role_weight",
           "squadron_ue", "positions", "unit_cost_lakh", "procurement_days", "position", "install_hours",
           "removal_hours", "hours_at_induction", "current_hours"}
INTEGERS = {"squadron_ue", "positions", "position"}
TIMES = {"install_time", "removal_time", "sent_time", "start_time", "done_time", "report_time", "receipt_time", "as_of"}
ORDER = MASTER_TABLES + EVENT_TABLES
HARD_ISSUES = ("NEG_INTERVAL", "BACKDATED_REMOVAL", "DUPLICATE_SPELL", "IMPLAUSIBLE_FH", "DOUBLE_INSTALL", "MISSING_KEY")


class RowError(ValueError):
    def __init__(self, issue: str, detail: str = ""):
        super().__init__(f"{issue}: {detail}")
        self.issue, self.detail = issue, detail


@dataclass
class BatchReport:
    file: str
    table: str
    rows: int = 0
    accepted: int = 0
    quarantined: int = 0
    skipped: bool = False
    issues: dict = field(default_factory=dict)
    batch: int | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Importer:
    def __init__(self, store: Store, mapping: str | Path | dict | None = None, ledger=None, signer=None):
        self.store = store
        if mapping is None or isinstance(mapping, (str, Path)):
            mapping = json.loads(Path(mapping or DEFAULT_MAPPING).read_text(encoding="utf-8"))
        self.mapping = mapping
        self.time_format = mapping.get("time_format", TIME_FMT)
        self.ledger, self.signer = ledger, signer

    # ------------------------------------------------------------ reference data

    def _refs(self) -> dict[str, dict]:
        q = self.store.con.execute
        return {
            "bases": {r[0] for r in q("SELECT base FROM bases")},
            "fleets": {r[0] for r in q("SELECT fleet FROM fleets")},
            "aircraft": {r[0]: r[1] for r in q("SELECT tail, fleet FROM aircraft")},
            "agencies": {r[0] for r in q("SELECT agency FROM agencies")},
            "parts": {r[0]: (r[1], r[2]) for r in q("SELECT pn, fleet, positions FROM parts")},
        }

    # ------------------------------------------------------------ one row

    def _convert(self, table: str, spec: dict, raw: dict) -> dict:
        row = {}
        for field_, col in spec["columns"].items():
            v = (raw.get(col) or "").strip()
            codes = spec.get("codes", {}).get(field_)
            if codes is not None:
                if v not in codes:
                    raise RowError("UNKNOWN_CODE", f"{col}={v!r}")
                v = codes[v]
            if field_ in spec.get("lists", {}):
                v = [x.strip() for x in v.split(spec["lists"][field_]) if x.strip()] if v else []
            row[field_] = v if v not in ("", None) else None
        for f in REQUIRED[table]:
            if row.get(f) in (None, "", []):
                raise RowError("MISSING_FIELD", f)
        for f in NUMBERS & row.keys():
            if row[f] is None:
                continue
            try:
                row[f] = int(float(row[f])) if f in INTEGERS else float(row[f])
            except ValueError:
                raise RowError("BAD_NUMBER", f"{f}={row[f]!r}") from None
        for f in TIMES & row.keys():
            if row[f] is None:
                continue
            try:
                row[f] = self._time(row[f])
            except ValueError:
                raise RowError("BAD_TIME", f"{f}={row[f]!r}") from None
        return row

    def _time(self, v: str) -> str:
        """Source time -> canonical text. Already canonical (the common case) is checked without strptime,
        which dominates large imports; anything else goes through the mapping's format."""
        if self.time_format == TIME_FMT and _CANONICAL.fullmatch(v):
            datetime(int(v[:4]), int(v[5:7]), int(v[8:10]), int(v[11:13]), int(v[14:16]))   # raises if invalid
            return v
        return datetime.strptime(v, self.time_format).strftime(TIME_FMT)

    def _check(self, table: str, row: dict, refs: dict) -> None:
        if table == "aircraft":
            if row["fleet"] not in refs["fleets"]:
                raise RowError("UNKNOWN_FLEET", row["fleet"])
            if row["base"] not in refs["bases"]:
                raise RowError("UNKNOWN_BASE", row["base"])
        elif table == "parts":
            if row["fleet"] not in refs["fleets"]:
                raise RowError("UNKNOWN_FLEET", row["fleet"])
            bad = [a for a in row["eligible_agencies"] + [row["default_agency"]] if a not in refs["agencies"]]
            if bad:
                raise RowError("UNKNOWN_AGENCY", ",".join(bad))
            if row["default_agency"] not in row["eligible_agencies"]:
                raise RowError("DEFAULT_NOT_APPROVED", row["default_agency"])
            if row["positions"] < 1:
                raise RowError("BAD_POSITIONS", str(row["positions"]))
        if table in EVENT_TABLES:
            pn = row.get("pn")
            if pn is not None and pn not in refs["parts"]:
                raise RowError("UNKNOWN_PART", pn)
            tail = row.get("tail")
            if tail is not None:
                if tail not in refs["aircraft"]:
                    raise RowError("UNKNOWN_AIRCRAFT", tail)
                if pn is not None and refs["parts"][pn][0] != refs["aircraft"][tail]:
                    raise RowError("PART_NOT_ON_TYPE", f"{pn} on {tail}")
            for f in ("base", "from_base"):
                if row.get(f) is not None and row[f] not in refs["bases"]:
                    raise RowError("UNKNOWN_BASE", row[f])
            if row.get("agency") is not None and row["agency"] not in refs["agencies"]:
                raise RowError("UNKNOWN_AGENCY", row["agency"])
        if table == "installs":
            if not 1 <= row["position"] <= refs["parts"][row["pn"]][1]:
                raise RowError("BAD_POSITION", f"{row['pn']} position {row['position']}")
            if row["install_hours"] < 0:
                raise RowError("NEGATIVE_HOURS", str(row["install_hours"]))
            if row.get("removal_time") is not None:
                if row["removal_time"] < row["install_time"]:
                    raise RowError("REMOVAL_BEFORE_INSTALL", f"{row['removal_time']} < {row['install_time']}")
                if row.get("removal_hours") is not None and row["removal_hours"] < row["install_hours"] - 1e-6:
                    raise RowError("HOURS_BACKWARDS", f"{row['removal_hours']} < {row['install_hours']}")
            elif row.get("removal_reason") is not None:
                raise RowError("REASON_WITHOUT_REMOVAL", row["removal_reason"])
            elif row.get("current_hours") is not None and row["current_hours"] < row["install_hours"] - 1e-6:
                raise RowError("HOURS_BACKWARDS", f"current {row['current_hours']} < {row['install_hours']}")
        elif table == "repair_orders":
            times = [row.get(k) for k in ("sent_time", "start_time", "done_time")]
            known = [t for t in times if t is not None]
            if known != sorted(known) or (times[2] is not None and times[1] is None):
                raise RowError("REPAIR_DATES_OUT_OF_ORDER", " / ".join(t or "-" for t in times))
        elif table == "defects" and row.get("problem_code"):
            row["problem_code"] = row["problem_code"].lower()

    # ------------------------------------------------------------ one file

    def import_file(self, folder: Path, rel: str, spec: dict) -> BatchReport:
        path = folder / rel
        table = spec["table"]
        rep = BatchReport(rel, table)
        if not path.exists():
            rep.skipped = True
            return rep
        sha = _sha256(path)
        if self.store.con.execute("SELECT 1 FROM ingest_batches WHERE sha256 = ? AND file = ?", (sha, rel)).fetchone():
            rep.skipped = True                         # same file already imported
            return rep
        refs = self._refs()
        good, bad, seen = [], [], set()
        with path.open(newline="", encoding="utf-8-sig") as f:
            for i, raw in enumerate(csv.DictReader(f), start=1):
                rep.rows += 1
                key = tuple(sorted(raw.items()))
                try:
                    if key in seen:
                        raise RowError("DUPLICATE_ROW", "identical to an earlier row")
                    seen.add(key)
                    row = self._convert(table, spec, raw)
                    self._check(table, row, refs)
                    good.append(row)
                    if table in MASTER_TABLES:           # later master rows may refer to earlier ones
                        _update_refs(refs, table, row)
                except RowError as e:
                    bad.append((i, e.issue, e.detail, raw))
                    rep.issues[e.issue] = rep.issues.get(e.issue, 0) + 1
        with self.store.tx() as con:
            cur = con.execute("INSERT INTO ingest_batches(source, file, sha256, at, rows, accepted, quarantined) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (spec.get("system", "unknown"), rel, sha, datetime.now().strftime(TIME_FMT),
                               rep.rows, len(good), len(bad)))
            batch = cur.lastrowid
            if table in MASTER_TABLES:
                for row in good:
                    _insert(con, table, row, batch)
            else:                                       # event rows: one statement per column set
                groups: dict[tuple, list] = {}
                for row in good:
                    groups.setdefault(tuple(row), []).append([batch] + [row[c] for c in row])
                for cols, rows in groups.items():
                    con.executemany(f"INSERT INTO {table}(batch,{','.join(cols)}) "
                                    f"VALUES ({','.join('?' * (len(cols) + 1))})", rows)
            con.executemany("INSERT INTO quarantine(batch, row_no, target, issue, detail, raw) VALUES (?,?,?,?,?,?)",
                            [(batch, i, table, issue, detail, json.dumps(raw)) for i, issue, detail, raw in bad])
        rep.accepted, rep.quarantined, rep.batch = len(good), len(bad), batch
        if self.ledger is not None and self.signer is not None:
            e = self.ledger.append("data_batch", {"source": spec.get("system"), "file": rel, "sha256": sha,
                                                  "rows": rep.rows, "accepted": rep.accepted,
                                                  "quarantined": rep.quarantined, "issues": rep.issues}, self.signer)
            self.store.con.execute("UPDATE ingest_batches SET ledger_seq = ? WHERE batch = ?", (e["seq"], batch))
            self.store.con.commit()
        return rep

    # ------------------------------------------------------------ a folder

    def import_folder(self, folder: str | Path) -> dict:
        folder = Path(folder)
        man = folder / "manifest.json"
        if man.exists():
            m = json.loads(man.read_text(encoding="utf-8"))
            if self.store.meta("epoch") is None and m.get("epoch"):
                self.store.set_meta("epoch", m["epoch"])
            if m.get("generator"):
                self.store.set_meta("generator", str(m["generator"]))
            if m.get("as_of") and (self.store.meta("as_of") or "") < m["as_of"]:
                self.store.set_meta("as_of", m["as_of"])
        risk = folder / "masters/supply_risk.json"
        if risk.exists():                      # supplier regime model: a planning assumption kept as master data
            self.store.set_meta("supply_risk", json.dumps(json.loads(risk.read_text(encoding="utf-8"))))
        specs = self.mapping["sources"]
        order = sorted(specs, key=lambda rel: ORDER.index(specs[rel]["table"]))
        reports = [self.import_file(folder, rel, specs[rel]) for rel in order]
        issues = self.cross_checks()
        return {"batches": [r.__dict__ for r in reports], "data_issues": issues, "counts": self.store.counts()}

    def cross_checks(self) -> dict[str, int]:
        """SATYA invariants across all loaded records, refreshed after every import."""
        fr = self.store.frames()
        sp, rp = fr["spells"], fr["repairs"]
        with self.store.tx() as con:
            con.execute("DELETE FROM data_issues WHERE resolved = 0")
        if sp.empty:
            return {}
        horizon = self.store.now_day()
        issues = check_spells(sp, rp, horizon_day=None if horizon != horizon else horizon)
        rows = []
        for r in issues.itertuples(index=False):
            frame = sp if r.table == "spells" else rp
            rows.append(("installs" if r.table == "spells" else "repair_orders",
                         int(frame.loc[r.row, "record_id"]), r.issue, r.serial, r.pn,
                         datetime.now().strftime(TIME_FMT)))
        with self.store.tx() as con:
            con.executemany("INSERT INTO data_issues(target, record_id, issue, serial, pn, found_at) "
                            "VALUES (?,?,?,?,?,?)", rows)
        out: dict[str, int] = {}
        for r in rows:
            out[r[2]] = out.get(r[2], 0) + 1
        return out


def _update_refs(refs: dict, table: str, row: dict) -> None:
    if table == "bases":
        refs["bases"].add(row["base"])
    elif table == "fleets":
        refs["fleets"].add(row["fleet"])
    elif table == "aircraft":
        refs["aircraft"][row["tail"]] = row["fleet"]
    elif table == "agencies":
        refs["agencies"].add(row["agency"])
    elif table == "parts":
        refs["parts"][row["pn"]] = (row["fleet"], row["positions"])


def _insert(con, table: str, row: dict, batch: int) -> None:
    row = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in row.items()}
    if table in MASTER_TABLES:
        key = REQUIRED[table][0]
        cols = list(row)
        con.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                    f"ON CONFLICT({key}) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in cols if c != key),
                    [row[c] for c in cols])
    else:
        cols = ["batch"] + list(row)
        con.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [batch] + [row[c] for c in cols[1:]])


def data_steward_summary(store: Store) -> dict:
    """What a data steward needs: rejected rows and open issues, grouped by reason."""
    q = store.con.execute
    return {
        "quarantined": {r[0]: r[1] for r in q("SELECT issue, COUNT(*) FROM quarantine GROUP BY issue ORDER BY 2 DESC")},
        "open_issues": {r[0]: r[1] for r in q("SELECT issue, COUNT(*) FROM data_issues WHERE resolved = 0 "
                                              "GROUP BY issue ORDER BY 2 DESC")},
        "batches": [dict(zip(("batch", "source", "file", "rows", "accepted", "quarantined"), r))
                    for r in q("SELECT batch, source, file, rows, accepted, quarantined FROM ingest_batches")],
    }
