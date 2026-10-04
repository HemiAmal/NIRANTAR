from nirantar.chanakya.mrv import (Pricer, consumption_portfolio, greedy_portfolio,
                                   surrogate_provision_values)
from nirantar.sanjaya.ensemble import P3, rar
from nirantar.sanjaya.twin import Action


def test_rar():
    r, c = rar([0.5, 0.6, 0.7, 0.8, 0.9, 0.55, 0.65, 0.75, 0.85, 0.95], alpha=0.2)
    assert c <= r <= 0.6


def test_null_action_has_zero_mrv(world, history, model):
    pr = Pricer(world, P3, 120, range(3), history.snapshot, model)
    r = pr.price(Action("provision", "FH-HP-03", "B1", 1, start_day=999, cost_lakh=15))
    assert r.mean_aad == 0.0 and r.per_seed == [0.0, 0.0, 0.0]


def test_portfolios_respect_budget(world, history, model, frames):
    vals = surrogate_provision_values(world, history.snapshot, model, 365)
    smart = greedy_portfolio(vals, 300, 365)
    cons = consumption_portfolio(world, frames["spells"], 300)
    assert 0 < sum(a.cost_lakh for a in smart) <= 300
    assert 0 < sum(a.cost_lakh for a in cons) <= 300


def test_cost_of_delay_mechanism(world, history, model):
    """Delaying an action past the horizon removes all of its value, so CoD = MRV / delay."""
    pr = Pricer(world, P3, 200, range(4), history.snapshot, model)
    per_day, now, later = pr.cost_of_delay(Action("provision", "HU-DA-07", "B3", 2, cost_lakh=10), 400)
    assert later.mean_aad == 0.0
    assert abs(per_day - now.mean_aad / 400) < 1e-9
