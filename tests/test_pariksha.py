"""Validation on real public data (PARIKSHA) and refitting."""
import json

import numpy as np
import pytest

from nirantar.chitragupta.ledger import Ledger, Signer
from nirantar.dhanvantari.tier_c import _Objective, build_design
from nirantar.pariksha import public as P
from nirantar.pariksha import studies as S
from nirantar.setu.export import export
from nirantar.setu.ingest import Importer
from nirantar.setu.refit import drift, refit
from nirantar.setu.schema import Store


def test_datasets_load_as_spells():
    sp, fam = P.genfan()
    assert len(sp) == 70 and (sp["removal_reason"] == "failure").sum() == 12
    sp, fam = P.valve_seat_spells(P.valve_seats())
    assert sp["serial"].nunique() == 41 and (sp["removal_reason"] == "failure").sum() == 48
    d = P.drives()
    assert len(d) == 52422 and d["status"].sum() == 2885 and d["model"].nunique() == 85


def test_weibull_mle_recovers_known_parameters():
    rng = np.random.default_rng(0)
    t = 1000 * rng.weibull(1.7, 4000)
    c = rng.uniform(0, 2000, 4000)
    b, e = S.weibull_mle(np.minimum(t, c), (t <= c).astype(float))
    assert b == pytest.approx(1.7, rel=0.05) and e == pytest.approx(1000, rel=0.05)


def test_fans_agree_with_an_independent_fit():
    r = S.fans()
    assert r["independent_mle"]["beta"] == pytest.approx(1.058, abs=0.002)
    assert r["max_abs_difference"] < 0.03                # failure probabilities, frailty integrated out


def test_part_shape_gradient_is_exact(world, history):
    from nirantar.records import to_frames
    d = build_design(to_frames(history.records)["spells"], {p: v.family for p, v in world.pns.items()})
    o = _Objective(d, part_shape=True)
    x = o.x0() + np.random.default_rng(1).normal(0, 0.05, len(o.x0()))
    _, g = o(x)
    for i in np.random.default_rng(2).choice(len(x), 12, replace=False):
        e = np.zeros(len(x)); e[i] = 1e-6
        assert (o(x + e)[0] - o(x - e)[0]) / 2e-6 == pytest.approx(g[i], abs=1e-4)


def test_hierarchical_fit_beats_pooling_on_held_out_drives():
    r = S.drives(seeds=(0,))
    run = r["runs"][0]
    best = run["tier_c_part_shape"]
    assert best["loglik_per_1000"] > run["complete_pooling"]["loglik_per_1000"]
    assert best["loglik_per_1000"] > run["no_pooling"]["loglik_per_1000"]
    assert best["deviance_by_model_sparse"] < run["no_pooling"]["deviance_by_model_sparse"]
    e, o = best["expected_vs_observed"]
    assert abs(e / o - 1) < 0.1


def test_unit_tendency_helps_predict_valve_seat_replacements():
    r = S.valve_seats(draws=500)
    t = r["total"]
    assert t["tier_c_unit"]["deviance"] < t["tier_c_population"]["deviance"] < t["constant_rate"]["deviance"]


def test_braking_batches_reported_with_uncertainty():
    r = S.braking_grids()
    lo, mid, hi = r["batch2_life_vs_batch1_90ci"]
    assert lo < mid < hi and r["batch2_shorter_with_90pct_confidence"] == (hi < 1)


def test_refit_backtests_registers_and_signs(world, history, tmp_path):
    out = tmp_path / "x"
    export(world, history.records, history.snapshot, 1825, out)
    st = Store(tmp_path / "s.db")
    Importer(st).import_folder(out)
    led, sig = Ledger(tmp_path / "l.jsonl"), Signer.generate("setu")
    c1 = refit(st, ledger=led, signer=sig, log=lambda *_: None)
    assert c1["version"] == 1 and set(c1["holdout"]["scores"]) == {"family_shape", "part_shape"}
    sc = c1["holdout"]["scores"][c1["spec"]]
    assert abs(sc["failures_expected"] / sc["failures_observed"] - 1) < 0.2
    assert json.loads(st.meta("model_spec"))["part_shape"] == (c1["spec"] == "part_shape")
    c2 = refit(st, ledger=led, signer=sig, log=lambda *_: None)
    assert c2["version"] == 2 and c2["drift"] == []          # same records: nothing moved
    assert [e["kind"] for e in led.entries] == ["model_fit", "model_fit"] and led.verify_all() == []


def test_drift_flags_only_real_moves():
    prev = {"eta": {"A": [1000.0, 0.05], "B": [500.0, 0.05]}, "q": {"G": [0.3, 0.1]}}
    cur = {"eta": {"A": [1300.0, 0.05], "B": [510.0, 0.05]}, "q": {"G": [0.32, 0.1]}}
    flags = drift(prev, cur)
    assert [f.get("part") for f in flags] == ["A"]
