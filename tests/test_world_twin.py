import numpy as np

from nirantar.sanjaya.ensemble import P0, P2, P3
from nirantar.sanjaya.twin import SUPPLY_SHOCK, Action, Twin, _accumulate


def test_world_shape(world):
    assert len(world.tails) == 70
    assert len(world.rogue_serials) == round(0.03 * len(world.serials))
    assert set(world.bases) == {"B1", "B2", "B3", "B4"}


def test_deterministic(world):
    a = Twin(world, P0, 200, seed=3).run()
    b = Twin(world, P0, 200, seed=3).run()
    assert a.aad == b.aad and a.failures == b.failures


def test_availability_bounds_and_conservation(world):
    tw = Twin(world, P0, 400, seed=4)
    r = tw.run()
    for v in r.fleet_daily_availability.values():
        assert np.all(v >= -1e-9) and np.all(v <= 1 + 1e-9)
    installed = sum(len(t["inst"]) for t in tw.tails)
    stock = sum(len(v) for v in tw.stock.values())
    pipeline = sum(1 for e in tw._events if e[2] in ("AG_ARRIVE", "REPAIR_DONE", "ARRIVE"))
    pipeline += sum(len(q) for q in tw.queues.values())
    assert installed + stock + pipeline == len(world.serials)


def test_supply_shock_hurts_reactive(world):
    seeds = range(6)
    normal = np.mean([Twin(world, P0, 365, seed=s).run().overall_availability for s in seeds])
    shock = np.mean([Twin(world, P0, 365, seed=s, scenario=SUPPLY_SHOCK).run().overall_availability for s in seeds])
    assert shock < normal


def test_snapshot_continuation(history, world, model):
    r = Twin(world, P3, 120, seed=5, start=history.snapshot, decision_model=model).run()
    assert 0.2 < r.overall_availability < 1.0


def test_policy_needs_model(world):
    import pytest
    with pytest.raises(ValueError):
        Twin(world, P2, 10, seed=1)


def test_provision_after_horizon_changes_nothing(world):
    a = Twin(world, P0, 100, seed=8).run()
    b = Twin(world, P0, 100, seed=8, actions=(Action("provision", "FH-HP-03", "B1", 2, start_day=500),)).run()
    assert a.aad == b.aad


def test_accumulate_bins():
    arr = np.zeros(4)
    _accumulate(arr, 0.5, 2.25)
    assert np.allclose(arr, [0.5, 1.0, 0.25, 0.0])


def test_forecast_continues_supply_regime(world):
    tw = Twin(world, P0, 400, seed=11)
    tw.run()
    snap = tw.snapshot()
    nxt = Twin(world, P0, 30, seed=12, start=snap)
    for c, state in snap["regimes"].items():
        assert nxt.regime_state[c][0] == state
