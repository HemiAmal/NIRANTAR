"""Scale: larger worlds, sub-fleet views, cached random draws and fleet-by-fleet plan pricing."""
import numpy as np
import pytest

from nirantar.bharat_fleet.scale import make_scaled_world
from nirantar.chanakya.desk import build_plan
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.records import to_frames
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Twin, first_normal, first_uniform, krng
from nirantar.sanjaya.views import fleet_view


@pytest.fixture(scope="module")
def small():
    w = make_scaled_world(n_fleets=3, n_bases=4, squadrons_per_fleet=2, pns_per_fleet=6, bases_per_fleet=2, seed=3)
    h = Twin(w, P0, 365, seed=5, record=True).run()
    m = fit_tier_c(to_frames(h.records)["spells"], {p: v.family for p, v in w.pns.items()}, hessian=False)
    return w, h.snapshot, m


def test_scaled_world_is_consistent(small):
    w, _, _ = small
    assert len(w.fleets) == 3 and len(w.pns) == 18
    assert len({t["id"] for t in w.tails}) == len(w.tails)
    for t in w.tails:
        assert w.fleets[t["fleet"]].tails_per_base[t["base"]] > 0
    for p in w.pns.values():
        assert p.default_agency in p.eligible_agencies


def test_cached_draws_equal_the_generator():
    for keys in [(1, "life", 3, "PN", 0, 2), (9, "tat", 77, 4, "BRD-1")]:
        assert first_uniform(keys) == krng(*keys).random()
        assert first_normal(keys) == krng(*keys).standard_normal()


def test_a_fleet_view_reproduces_that_fleet(small):
    w, start, _ = small
    for s in range(2):
        full = Twin(w, P0, 60, seed=s, start=start, resume=True).run()
        for f in w.fleets:
            sw, ss = fleet_view(w, start, [f])
            sub = Twin(sw, P0, 60, seed=s, start=ss, resume=True).run()
            assert np.allclose(sub.fleet_daily_availability[f], full.fleet_daily_availability[f])


def test_pricing_by_fleet_gives_the_same_plan(small):
    w, start, m = small
    kw = dict(horizon=45, n_seeds=6, n_screen=3, workers=1, prune=False)
    a = build_plan(w, start, m, P0, dict(m.n_failures_by_pn), {}, decompose=False, **kw)
    b = build_plan(w, start, m, P0, dict(m.n_failures_by_pn), {}, decompose=True, **kw)
    assert b["priced_by_fleet"] and not a["priced_by_fleet"]
    assert [i["label"] for i in a["items"]] == [i["label"] for i in b["items"]]
    assert [i["mrv"] for i in a["items"]] == [i["mrv"] for i in b["items"]]
