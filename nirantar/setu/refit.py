"""Refitting: re-estimate the reliability model as records arrive, and prove it on records it has not seen.

``refit(store)``:

1. **Back-test inside the store.** Fit each candidate model specification on
   the records up to ``as_of - holdout_days`` and score it on what happened
   after: the held-out log-likelihood of every unit at risk at the cut-off
   (left-truncated at its age then, with its own failure tendency from before),
   and expected against observed failures per part number.
2. **Choose** the specification with the best held-out score, and refit it on
   all records.
3. **Compare** with the previous registered model: part numbers whose life
   (eta) or agencies whose repair quality (q) moved by more than two standard
   errors are flagged as drift for a reliability engineer to review.
4. **Register** the model card (data fingerprint, specification, scores, key
   parameters) in the store, and sign it into the ledger as ``model_fit``.

The planner then uses the registered specification (``estimate`` reads it).
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime

import numpy as np
import pandas as pd

from nirantar.dhanvantari.tier_c import TierCModel, fit_tier_c
from nirantar.setu.schema import TIME_FMT, Store

SPECS = {"family_shape": {"part_shape": False}, "part_shape": {"part_shape": True}}

REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS models (
  version INTEGER PRIMARY KEY, fitted_at TEXT NOT NULL, as_of TEXT, data_sha256 TEXT NOT NULL,
  spec TEXT NOT NULL, card TEXT NOT NULL, ledger_seq INTEGER);
"""


def _hours_at(sp: pd.DataFrame, day, now: float) -> pd.Series:
    """Unit hours at a day inside each spell, interpolated between installation and removal (or the last
    reading at the as-of time); flying is close to linear in calendar time over a spell."""
    end = sp["removal_day"].fillna(now)
    frac = ((day - sp["install_day"]) / (end - sp["install_day"]).clip(lower=1e-6)).clip(0, 1)
    return sp["entry_fh"] + frac * (sp["exit_fh"] - sp["entry_fh"])


def _truncate(spells: pd.DataFrame, t: float, now: float) -> pd.DataFrame:
    """The spells as the records stood at day t: later installations dropped, later removals still open."""
    sp = spells[(spells["install_day"] < t) & np.isfinite(spells["exit_fh"])].copy()
    still = sp["removal_day"].isna() | (sp["removal_day"] > t)
    sp.loc[still, "exit_fh"] = _hours_at(sp[still], t, now)
    sp.loc[still, "removal_reason"] = None
    sp.loc[still, "removal_day"] = np.nan
    return sp


def holdout_score(model: TierCModel, spells: pd.DataFrame, t: float, now: float) -> dict:
    """Score a model fitted on records up to day t on what happened between t and now.

    Every spell in service after t contributes d*log h(a_end) - [Lambda(a_end) - Lambda(a_t)] (left-truncated
    at its age at t), with the unit's own failure tendency estimated from before t. Virtual age from earlier
    repairs is left out: it is a common offset for the candidate models compared."""
    rows = spells[((spells["removal_day"].isna()) | (spells["removal_day"] > t)) & np.isfinite(spells["exit_fh"])]
    a0s = _hours_at(rows, np.maximum(rows["install_day"], t), now)
    k = model.frailty_k
    before = spells[spells["removal_day"] <= t]
    lam_before = _unit_hazard(model, before)
    n_before = before[before["removal_reason"] == "failure"].groupby("serial").size()
    ll, exp_by, obs_by = 0.0, {}, {}
    for r, a0 in zip(rows.itertuples(), a0s):
        a1 = r.exit_fh
        if a1 <= a0:
            continue
        beta, eta = model.params(r.pn, r.env)
        z = (k + n_before.get(r.serial, 0)) / (k + lam_before.get(r.serial, 0.0))
        dlam = z * ((a1 / eta) ** beta - (max(a0, 0.0) / eta) ** beta)
        fail = r.removal_reason == "failure"
        ll += (math.log(z * beta / eta) + (beta - 1) * math.log(a1 / eta) if fail else 0.0) - dlam
        exp_by[r.pn] = exp_by.get(r.pn, 0.0) + dlam
        obs_by[r.pn] = obs_by.get(r.pn, 0) + int(fail)
    pns = sorted(exp_by)
    obs = np.array([obs_by[p] for p in pns], float)
    exp = np.clip(np.array([exp_by[p] for p in pns]), 1e-9, None)
    dev = float(2 * np.sum(np.where(obs > 0, obs * np.log(np.where(obs > 0, obs, 1) / exp), 0) - (obs - exp)))
    return {"loglik": round(ll, 2), "failures_observed": int(obs.sum()), "failures_expected": round(float(exp.sum()), 1),
            "deviance_by_part": round(dev, 2),
            "by_part": {p: [round(float(e), 1), int(o)] for p, e, o in zip(pns, exp, obs)}}


def _unit_hazard(model: TierCModel, done: pd.DataFrame) -> dict:
    done = done[np.isfinite(done["exit_fh"])]
    lam = {}
    for r in done.itertuples():
        beta, eta = model.params(r.pn, r.env)
        lam[r.serial] = lam.get(r.serial, 0.0) + (max(r.exit_fh, 0) / eta) ** beta - (max(r.entry_fh, 0) / eta) ** beta
    return lam


def _key_params(m: TierCModel) -> dict:
    o = m._offset("log_eta")
    return {"eta": {p: [round(float(math.exp(m.log_eta_p[i])), 1), round(float(math.sqrt(max(m.cov[o + i, o + i], 0))), 4)]
                    for p, i in m._pn.items()},
            "beta": {p: round(m.params(p, "")[0], 3) for p in m.pns},
            "q": {a: [round(v, 3), round(float(math.sqrt(max(m.cov[m._offset("q") + j, m._offset("q") + j], 0))), 4)]
                  for j, (a, v) in enumerate(m.q_hat.items())},
            "frailty_k": round(m.frailty_k, 2), "n_failures": m.n_failures}


def drift(prev: dict, cur: dict, z: float = 2.0) -> list[dict]:
    """Parameters that moved by more than z combined standard errors since the previous model."""
    out = []
    for p, (eta, se) in cur["eta"].items():
        if p in prev["eta"]:
            e0, s0 = prev["eta"][p]
            d = math.log(eta) - math.log(e0)
            sd = math.hypot(se, s0)
            if sd > 0 and abs(d) > z * sd:
                out.append({"what": "life", "part": p, "from": e0, "to": eta, "change": f"{math.exp(d) - 1:+.0%}"})
    for a, (q, se) in cur["q"].items():
        if a in prev["q"]:
            q0, s0 = prev["q"][a]
            lq, lq0 = math.log(q / (1 - q)), math.log(q0 / (1 - q0))
            sd = math.hypot(se, s0)
            if sd > 0 and abs(lq - lq0) > z * sd:
                out.append({"what": "repair quality", "agency": a, "from": q0, "to": q})
    return out


def data_fingerprint(spells: pd.DataFrame) -> str:
    cols = ["serial", "pn", "install_day", "removal_day", "entry_fh", "exit_fh", "removal_reason"]
    return hashlib.sha256(pd.util.hash_pandas_object(spells[cols], index=False).values.tobytes()).hexdigest()


def refit(store: Store, holdout_days: float = 365.0, ledger=None, signer=None, log=print) -> dict:
    store.con.executescript(REGISTRY_DDL)
    fr, ms = store.frames(), store.masters()
    family_of = ms["parts"].set_index("pn")["family"].to_dict()
    sp = fr["spells"]
    now = store.now_day()
    t = now - holdout_days
    t0 = time.time()
    trunc = _truncate(sp, t, now)
    scores = {}
    for name, spec in SPECS.items():
        m = fit_tier_c(trunc, family_of, hessian=False, **spec)
        scores[name] = holdout_score(m, sp, t, now)
        log(f"  {name}: held-out log-likelihood {scores[name]['loglik']}, failures expected "
            f"{scores[name]['failures_expected']} vs observed {scores[name]['failures_observed']}")
    chosen = max(scores, key=lambda k: scores[k]["loglik"])
    model = fit_tier_c(sp, family_of, **SPECS[chosen])
    params = _key_params(model)
    prev = store.con.execute("SELECT version, card FROM models ORDER BY version DESC LIMIT 1").fetchone()
    flags = drift(json.loads(prev[1])["params"], params) if prev else []
    card = {"version": (prev[0] + 1) if prev else 1, "spec": chosen, "as_of": store.meta("as_of"),
            "holdout": {"from_day": round(t, 1), "to_day": round(now, 1), "scores": scores},
            "params": params, "drift": flags, "previous_version": prev[0] if prev else None,
            "fit_seconds": round(time.time() - t0, 1)}
    sha = data_fingerprint(sp)
    seq = None
    if ledger is not None and signer is not None:
        e = ledger.append("model_fit", {"model": "DHANVANTARI Tier C", "version": card["version"], "spec": chosen,
                                        "as_of": card["as_of"], "data_sha256": sha,
                                        "holdout_loglik": {k: v["loglik"] for k, v in scores.items()},
                                        "drift": flags}, signer)
        seq = e["seq"]
    with store.tx() as con:
        con.execute("INSERT INTO models(version, fitted_at, as_of, data_sha256, spec, card, ledger_seq) "
                    "VALUES (?,?,?,?,?,?,?)", (card["version"], datetime.now().strftime(TIME_FMT), card["as_of"],
                                               sha, chosen, json.dumps(card), seq))
    store.set_meta("model_spec", json.dumps(SPECS[chosen]))
    card["data_sha256"], card["ledger_seq"] = sha, seq
    return card
