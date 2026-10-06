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


def test_regime_belief_is_a_distribution_and_drives_the_futures(world, history, est):
    probs = est.start["regime_probs"]
    assert set(probs) == {c for c, m in world.regimes.items() if len(m.states) > 1}
    for c, p in probs.items():
        assert sum(p) == pytest.approx(1.0, abs=1e-3) and int(np.argmax(p)) == est.start["regimes"][c]
    certain = {**est.start, "regime_probs": {c: [0.0] * (len(p) - 1) + [1.0] for c, p in probs.items()}}
    for s in range(4):
        t = Twin(est.world, P0, 5, seed=s, start=certain, resume=True)
        assert all(t.regime_state[c][0] == len(p) - 1 for c, p in probs.items())


def test_backtest_runs_end_to_end(world):
    from nirantar.setu.backtest import backtest_cutoff
    r = backtest_cutoff(world, 400, horizon=30, plan_seeds=4, score_seeds=4, workers=1, log=lambda *_: None)
    assert r["state"]["fitted_units_correct"] == 1.0 and r["state"]["waiting_correct"] == 1.0
    d = r["decisions"]
    assert {"records_plan", "oracle_plan", "oracle_regime_as_records", "regret_wAAD"} <= set(d)
