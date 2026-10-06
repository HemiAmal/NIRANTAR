"""The console run from a record store: nothing taken from the simulator's hidden truth."""
import pytest

from nirantar.bharat_fleet.world import make_world
from nirantar.pipeline import Config, run
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Twin
from nirantar.setu.export import export
from nirantar.setu.ingest import Importer
from nirantar.setu.schema import Store
from nirantar.ui.server import Console


@pytest.fixture(scope="module")
def console(tmp_path_factory):
    out = tmp_path_factory.mktemp("results")
    run(Config(history_days=730, n_seeds=2, mrv_seeds=2, top_k=2, out_dir=str(out)), log=lambda *_: None)
    w = make_world(seed=7)
    h = Twin(w, P0, 730, seed=99, record=True).run()
    export(w, h.records, h.snapshot, 730, out / "exports")
    Importer(Store(out / "s.db")).import_folder(out / "exports")
    return Console(out, plan_kwargs={"n_seeds": 4, "n_screen": 2, "workers": 1}, store=out / "s.db")


def test_source_is_the_record_store(console):
    src = console.source()
    assert src["mode"] == "records" and "synthetic" in src["generator"].lower()
    ctx = console.sim_context()
    assert ctx["world"].serial_names and console.source()["notes"]
    assert console.state_dir.name == "records"


def test_plan_and_clock_run_on_estimates(console):
    desk = console.planner()
    plan = desk.build()
    assert plan["n_candidates"] > 0
    for it in plan["items"]:
        if it["kind"] in ("expedite", "priority"):
            assert "S/N SN-" in it["text"]
    clk = console.clock()
    d0 = clk.day
    console.advance({"days": 1})
    assert console.clock().day == d0 + 1


def test_saarthi_reads_recorded_serials(console):
    desk = console.desk()
    w = desk.w
    tail, slots = next((t, s) for t, s in desk.installed.items() if s)
    (pn, k), sid = next(iter(slots.items()))
    plate = w.sn(sid)
    r = desk.check({"tail": tail, "part": pn, "position": k + 1, "serial": plate})
    assert r["fields"]["serial"] == plate and r["serial_on_record"] == plate
    assert any(c["id"] == "serial" and c["status"] == "good" for c in r["checks"])
    digits = str(int(plate[3:]))                     # spoken as a number
    r = desk.check({"tail": tail, "part": pn, "position": k + 1, "serial": digits})
    assert r["fields"]["serial"] == plate
