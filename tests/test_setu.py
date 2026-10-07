import csv
import json
import shutil
from collections import Counter

import pytest

from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.records import to_frames
from nirantar.setu.export import export
from nirantar.setu.ingest import DEFAULT_MAPPING, Importer, data_steward_summary
from nirantar.setu.schema import Store

PLANTED_TO_ISSUE = {"UNKNOWN_PART": "UNKNOWN_PART", "BAD_TIME": "BAD_TIME", "BAD_POSITION": "BAD_POSITION",
                    "REMOVAL_BEFORE_INSTALL": "REMOVAL_BEFORE_INSTALL", "DUPLICATE": "DUPLICATE_ROW"}


@pytest.fixture(scope="module")
def exported(world, history, tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    man = export(world, history.records, history.snapshot, 1825, out)
    return out, man


def test_clean_import_reproduces_the_models(world, history, exported, tmp_path, family_of):
    out, man = exported
    st = Store(tmp_path / "s.db")
    rep = Importer(st).import_folder(out)
    assert sum(b["quarantined"] for b in rep["batches"]) == 0 and rep["data_issues"] == {}
    fr, db = to_frames(history.records), st.frames()
    assert len(db["spells"]) == len(fr["spells"]) and len(db["repairs"]) == len(fr["repairs"])
    a, b = fit_tier_c(fr["spells"], family_of), fit_tier_c(db["spells"], family_of)
    assert a.n_failures == b.n_failures
    for g in a.q_hat:
        assert b.q_hat[g] == pytest.approx(a.q_hat[g], abs=0.01)
    assert st.now_day() == pytest.approx(1825)


def test_planted_defects_are_quarantined_with_their_reason(world, history, tmp_path):
    out = tmp_path / "bad"
    man = export(world, history.records, history.snapshot, 1825, out, defect_rate=0.02, seed=3)
    st = Store(tmp_path / "s.db")
    rep = Importer(st).import_folder(out)
    ins = next(b for b in rep["batches"] if b["table"] == "installs")
    want = Counter(PLANTED_TO_ISSUE[p["kind"]] for p in man["planted_defects"])
    assert Counter(ins["issues"]) == want                        # every planted row caught, nothing else
    rows = {r[0] for r in st.con.execute("SELECT row_no FROM quarantine")}
    assert rows == {p["row"] for p in man["planted_defects"]}
    s = data_steward_summary(st)
    assert sum(s["quarantined"].values()) == len(man["planted_defects"])


def test_same_file_twice_is_ignored_and_batches_are_signed(exported, tmp_path):
    out, _ = exported
    st = Store(tmp_path / "s.db")
    led = Ledger(tmp_path / "l.jsonl")
    imp = Importer(st, ledger=led, signer=Signer.generate("setu"))
    first = imp.import_folder(out)
    n = st.counts()
    again = imp.import_folder(out)
    assert all(b["skipped"] for b in again["batches"]) and st.counts() == n
    batches = [e for e in led.entries if e["kind"] == "data_batch"]
    assert len(batches) == len([b for b in first["batches"] if not b["skipped"]]) and led.verify_all() == []


def test_a_renamed_export_needs_only_a_mapping(exported, tmp_path):
    """A source with different column names and codes is connected by configuration, not code."""
    out, _ = exported
    mapping = json.loads(DEFAULT_MAPPING.read_text())
    spec = mapping["sources"].pop("emms/installs.csv")
    renamed = {v: "X_" + v for v in spec["columns"].values()}
    spec["columns"] = {k: renamed[v] for k, v in spec["columns"].items()}
    spec["codes"]["removal_reason"] = {"U/S": "failure", "PM": "preventive", "CN": "cannibalised", "": None}
    mapping["sources"]["other/fitted.csv"] = spec
    recode = {"FAIL": "U/S", "PREV": "PM", "CANN": "CN", "": ""}
    (tmp_path / "other").mkdir()
    with (out / "emms/installs.csv").open() as f, (tmp_path / "other/fitted.csv").open("w", newline="") as g:
        r, w = csv.DictReader(f), None
        for row in r:
            row["REMOVECODE"] = recode[row["REMOVECODE"]]
            row = {renamed[k]: v for k, v in row.items()}
            if w is None:
                w = csv.DictWriter(g, fieldnames=list(row))
                w.writeheader()
            w.writerow(row)
    for d in ("masters", "emms", "immols"):
        shutil.copytree(out / d, tmp_path / d)
    (tmp_path / "manifest.json").write_text((out / "manifest.json").read_text())
    st_a, st_b = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    Importer(st_a).import_folder(out)
    Importer(st_b, mapping=mapping).import_folder(tmp_path)
    assert st_a.counts() == st_b.counts()


def test_cross_record_checks_find_a_unit_on_two_aircraft(exported, tmp_path):
    out, _ = exported
    st = Store(tmp_path / "s.db")
    imp = Importer(st)
    imp.import_folder(out)
    a = st.con.execute("SELECT serial, pn, tail, position, install_time, install_hours, removal_time, removal_hours, "
                       "removal_reason, current_hours FROM installs WHERE removal_time IS NOT NULL LIMIT 1").fetchone()
    other = st.con.execute("SELECT tail FROM aircraft WHERE fleet = (SELECT fleet FROM aircraft WHERE tail = ?) "
                           "AND tail != ? LIMIT 1", (a[2], a[2])).fetchone()[0]
    st.con.execute("INSERT INTO installs(batch, serial, pn, tail, position, install_time, install_hours, removal_time,"
                   " removal_hours, removal_reason, current_hours) VALUES (0,?,?,?,?,?,?,?,?,?,?)",
                   (a[0], a[1], other, a[3], a[4], a[5], a[6], a[7], a[8], a[9]))
    st.con.commit()
    issues = imp.cross_checks()
    assert issues.get("DOUBLE_INSTALL", 0) >= 2
    assert data_steward_summary(st)["open_issues"]["DOUBLE_INSTALL"] == issues["DOUBLE_INSTALL"]
