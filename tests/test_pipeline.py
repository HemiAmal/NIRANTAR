import json

from nirantar.pipeline import Config, run


def test_pipeline_smoke(tmp_path):
    cfg = Config(history_days=730, n_seeds=2, mrv_seeds=2, top_k=2, out_dir=str(tmp_path))
    out = run(cfg, log=lambda *_: None)
    rep = json.loads((tmp_path / "milestone1_report.json").read_text())
    assert {"experiment", "opportunities", "indigenisation", "ledger"} <= set(rep)
    assert rep["ledger"]["verify_all"] == []
    assert len(rep["experiment"]) == 14
    assert "Four-policy experiment" in out.markdown
