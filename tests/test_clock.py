import pytest

from nirantar.sanjaya.clock import OperationsClock
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Action, Twin


@pytest.fixture()
def clock(world, history, tmp_path):
    return OperationsClock(world, P0, history.snapshot, tmp_path / "live" / "clock.pkl")


def test_no_decisions_means_no_gap(clock):
    clock.advance(3)
    clock.advance(7)
    v = clock.view()
    assert v["day"] == 10 and len(v["log"]) == 10
    assert all(r["live"] == r["shadow"] for r in v["log"]) and v["waad_gained"] == 0


def test_waiting_time_carries_across_days(clock):
    before = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in clock.snapshot["waiting"]}
    clock.advance(3)
    after = {(w["tail"], w["pn"], w["pos"]): w["days"] for w in clock.snapshot["waiting"]}
    still = set(before) & set(after)
    assert still and all(after[k] == pytest.approx(before[k] + 3) for k in still)


def _cann(world, snap):
    tails = {t["id"]: t for t in world.tails}
    by_tail = {}
    for w in snap["waiting"]:
        by_tail.setdefault(w["tail"], []).append(w["pn"])
    for r, r_pns in by_tail.items():
        for d, d_pns in by_tail.items():
            pn = r_pns[0]
            if d != r and tails[d]["base"] == tails[r]["base"] and tails[d]["fleet"] == tails[r]["fleet"] \
                    and pn not in d_pns and any(s[0] == pn for s in snap["installed"][d]):
                return Action("cann", pn, base=tails[r]["base"], src=d, tail=r)
    pytest.skip("no cannibalisation pair")


def test_decisions_open_a_gap_on_identical_events(world, clock):
    a = _cann(world, clock.snapshot)
    clock.advance(7, (a,), ({"recommendation_seq": 5, "text": "test"},))
    v = clock.view()
    assert v["waad_gained"] > 0 and v["waiting_live"] < v["waiting_shadow"]
    assert v["applied"][0]["recommendation_seq"] == 5 and clock.applied_seqs() == {5}
    assert any(e["kind"] == "applied" for e in v["events"])


def test_purchases_survive_the_next_day(world, clock):
    clock.advance(2, (Action("provision", "HU-DA-07", base="B3", qty=2, cost_lakh=10),), ({"text": "buy"},))
    n = len(clock.snapshot["V"])
    assert n == len(world.serials) + 2 and len(clock.snapshot["new_pn"]) == 2
    clock.advance(30)                                  # continuing from a state with new units works
    assert len(clock.snapshot["V"]) >= n


def test_persistence_reset_and_limits(world, history, tmp_path):
    path = tmp_path / "c.pkl"
    c = OperationsClock(world, P0, history.snapshot, path)
    c.advance(1)
    again = OperationsClock(world, P0, history.snapshot, path)
    assert again.day == 1 and len(again.view()["log"]) == 1
    with pytest.raises(ValueError):
        again.advance(0)
    again.reset()
    assert not path.exists() and OperationsClock(world, P0, history.snapshot, path).day == 0


def test_resume_off_by_default(world, history):
    s = history.snapshot
    a = Twin(world, P0, 20, seed=4, start=s).run().waad
    assert a == Twin(world, P0, 20, seed=4, start=s).run().waad
