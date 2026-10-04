import pandas as pd

from nirantar.drishti.signals import disproportionality, exposure_rates, ic_interval
from nirantar.satya.quality import check_spells, evidence_grade, inject_defects


def test_ic_interval():
    ic, lo, hi = ic_interval(20, 5)
    assert lo < ic < hi and lo > 0
    ic, lo, hi = ic_interval(5, 5)
    assert lo < 0 < hi


def test_strong_effect_is_signal_and_null_is_not():
    rows = []
    for env, n_c, n_w in (("coastal", 40, 20), ("desert", 5, 60), ("hill", 6, 60)):
        rows += [{"family": "drive", "env": env, "mode": "corrosion"}] * n_c
        rows += [{"family": "drive", "env": env, "mode": "wear"}] * n_w
    sig = disproportionality(pd.DataFrame(rows))
    top = sig[sig["signal"]]
    assert ((top["env"] == "coastal") & (top["mode"] == "corrosion")).any()
    null = pd.DataFrame([{"family": "drive", "env": e, "mode": m} for e in ("a", "b", "c")
                         for m in ("x", "y") for _ in range(30)])
    assert not disproportionality(null)["signal"].any()


def test_history_signals_have_no_false_alarms(frames, family_of, world):
    sig = disproportionality(frames["snags"], exposure=exposure_rates(frames["spells"], family_of))
    planted = {(f, e, world.env_mode_boost[(f, e)]) for (f, e) in world.env_mode_boost}
    found = {tuple(x) for x in sig[sig["signal"]][["family", "env", "mode"]].values}
    assert found and found <= planted


def test_clean_records_pass(frames):
    issues = check_spells(frames["spells"], frames["repairs"], horizon_day=1825)
    assert issues.empty


def test_injected_defects_caught(frames):
    bad, truth = inject_defects(frames["spells"], rate=0.03, seed=2)
    issues = check_spells(bad, frames["repairs"], horizon_day=1825)
    assert truth["row"].isin(set(issues["row"])).mean() == 1.0


def test_evidence_grades():
    assert evidence_grade(0.95, 80, 3.0).grade == "E1"
    assert evidence_grade(0.85, 25).grade == "E2"
    assert evidence_grade(0.7, 10).grade == "E3"
    assert evidence_grade(0.6, 2).grade == "E4"
    assert evidence_grade(0.4, 500).grade == "E5"
