import numpy as np
from scipy.optimize import check_grad

from nirantar.dhanvantari.tier_c import _Objective, build_design
from nirantar.sushruta.agency import agency_scorecards, flag_rogues, serial_frailty


def test_gradient_is_exact(frames, family_of):
    obj = _Objective(build_design(frames["spells"], family_of))
    x = obj.x0() + np.random.default_rng(0).normal(0, 0.1, len(obj.x0()))
    err = check_grad(lambda v: obj(v)[0], lambda v: obj(v)[1], x)
    assert err / max(np.linalg.norm(obj(x)[1]), 1.0) < 1e-4


def test_agency_quality_ranking(model, world):
    q = model.q_hat
    assert q["MSME-P"] == max(q.values())                   # the poor repairer is found
    assert q["MSME-P"] > q["HAL-K"] and q["BRD-1"] > q["HAL-K"]
    lo, hi = model.q_interval("MSME-P")[1:]
    assert lo < world.agencies["MSME-P"].q < hi


def test_environment_effect_found(model):
    est, lo, hi = model.env_multiplier("drivetrain", "coastal_saline")
    assert hi < 1.0                                         # salinity shortens life, CI excludes 1
    est, lo, hi = model.env_multiplier("rotor", "high_altitude")
    assert hi < 1.0


def test_weibull_shape_recovered(model, world):
    for pn in ("FH-RD-05", "HU-DA-07"):
        beta, _ = model.params(pn, "desert_dust")
        assert abs(beta - world.pns[pn].beta) < 0.35


def test_fail_prob_monotone(model):
    p1 = model.fail_prob("FH-HP-03", "desert_dust", 100, 50)
    p2 = model.fail_prob("FH-HP-03", "desert_dust", 400, 50)
    assert 0 < p1 < p2 < 1
    est, lo, hi = model.fail_prob_interval("FH-HP-03", "desert_dust", 400, 50, n_draws=50)
    assert lo <= est <= hi


def test_rogue_detection_precise(model, frames, family_of, world):
    flags = flag_rogues(serial_frailty(model, frames["spells"], family_of), p_min=0.5)
    assert len(flags) > 0
    precision = len(flags & world.rogue_serials) / len(flags)
    assert precision >= 0.7


def test_scorecards(model, frames):
    sc = agency_scorecards(model, frames["repairs"])
    assert set(sc["agency"]) == set(model.agencies)
    assert (sc["q_lo"] <= sc["q_hat"]).all() and (sc["q_hat"] <= sc["q_hi"]).all()
