import numpy as np
import pytest

from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Twin
from nirantar.setu.estimate import estimate
from nirantar.setu.export import export, serial_id
from nirantar.setu.ingest import Importer
from nirantar.setu.schema import Store


@pytest.fixture(scope="module")
def est(world, history, tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    export(world, history.records, history.snapshot, 1825, out)
    st = Store(out / "store.db")
    Importer(st).import_folder(out)
    return estimate(st)


def test_fleet_state_is_rebuilt_from_records(history, est):
    truth, got = history.snapshot, est.start
    sid = lambda i: est.id_of[serial_id(i)]
    for tail, inst in truth["installed"].items():
        assert {tuple(k): sid(v) for k, v in inst.items()} == got["installed"].get(tail, {})
    assert {k: sorted(map(sid, v)) for k, v in truth["stock"].items()} == {k: sorted(v) for k, v in got["stock"].items()}
    assert {(sid(p["sid"]), p["type"]) for p in truth["pipeline"]} == {(p["sid"], p["type"]) for p in got["pipeline"]}
    tw = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in truth["waiting"]}
    gw = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in got["waiting"]}
    assert tw.keys() == gw.keys() and all(abs(tw[k] - gw[k]) < 0.01 for k in tw)
    assert got["regimes"] == truth["regimes"]
    i = [k for k in range(len(truth["X"])) if serial_id(k) in est.id_of]
    assert np.abs(truth["X"][i] - got["X"][[sid(k) for k in i]]).max() < 0.05


def test_agency_and_unit_estimates_are_close_to_the_hidden_truth(world, est):
    st = est.agency_stats.set_index("agency")
    for a in world.agencies.values():
        assert st.loc[a.id, "tat_median"] == pytest.approx(a.tat_median_days, rel=0.15)
        assert st.loc[a.id, "back_leg_base"] == pytest.approx(a.transport_days, rel=0.25)
    flagged = {int(est.serial_of[i][3:]) for i in est.world.rogue_serials}
    assert len(flagged & world.rogue_serials) >= 0.8 * len(flagged)             # same detector as the analysis
    assert len(flagged & world.rogue_serials) >= 0.4 * len(world.rogue_serials)
    assert est.world.sn(next(iter(est.world.rogue_serials))).startswith("SN-")


def test_the_twin_runs_from_the_estimate_and_forecasts_like_the_truth(world, history, est):
    H, seeds = 90, range(8)
    a = np.mean([Twin(world, P0, H, seed=s, start=history.snapshot, resume=True).run().overall_availability
                 for s in seeds])
    b = np.mean([Twin(est.world, P0, H, seed=s, start=est.start, resume=True).run().overall_availability
                 for s in seeds])
    assert abs(a - b) < 0.04


def test_without_a_supplier_risk_master_everything_is_assumed_normal(world, history, tmp_path):
    out = tmp_path / "x"
    export(world, history.records, history.snapshot, 1825, out)
    (out / "masters/supply_risk.json").unlink()
    st = Store(tmp_path / "s.db")
    Importer(st).import_folder(out)
    e = estimate(st)
    assert set(e.start["regimes"].values()) == {0}
    assert any("risk" in n for n in e.notes)
