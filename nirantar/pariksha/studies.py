"""PARIKSHA: does DHANVANTARI hold up on real records?

Four studies on real public field data (``datasets/SOURCES.md``), each scored on
records the fit did not see:

1. **Fans**: the fit against an independent maximum-likelihood Weibull fit
   (a check that the code estimates what it claims to).
2. **Drives**: 52k drives of 85 models. Held-out drives, predicted failure
   probabilities, against no pooling (a separate fit per model) and complete
   pooling (one fit for all). Sparse part numbers are where pooling must help;
   the test is repeated with a 10% training sample.
3. **Valve seats**: back-test at three cut-off days. Each engine's replacements
   after the cut-off are predicted from its record before it, with and without
   the unit's own failure tendency (the frailty behind rogue-unit detection).
4. **Braking grids**: can a worse manufacturing batch be told apart, with
   uncertainty?
"""
from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from nirantar.dhanvantari.tier_c import TierCModel, fit_tier_c
from nirantar.pariksha import public as P


# ---------------------------------------------------------------- helpers


def weibull_mle(t: np.ndarray, d: np.ndarray) -> tuple[float, float]:
    """Plain censored Weibull maximum likelihood (no priors, no frailty): (beta, eta)."""
    t, d = np.asarray(t, float), np.asarray(d, float)

    def nll(x):
        b, e = math.exp(x[0]), math.exp(x[1])
        return -(np.sum(d * (math.log(b) - b * x[1] + (b - 1) * np.log(t))) - np.sum((t / e) ** b))

    best = None
    for b0 in (0.7, 1.0, 1.5, 2.5):
        r = minimize(nll, [math.log(b0), math.log(t.mean() * 2)], method="Nelder-Mead",
                     options={"xatol": 1e-9, "fatol": 1e-9, "maxiter": 10_000})
        if best is None or r.fun < best.fun:
            best = r
    return math.exp(best.x[0]), math.exp(best.x[1])


def _marginal_fail(model: TierCModel, pn: str, env: str, t: np.ndarray, frailty: bool = True) -> np.ndarray:
    """P(failure by age t) for a new unit, the unit's own frailty integrated out."""
    beta, eta = model.params(pn, env)
    lam = (np.asarray(t, float) / eta) ** beta
    if not frailty:
        return 1 - np.exp(-lam)
    k = model.frailty_k
    return 1 - (1 + lam / k) ** (-k)


def _poisson_dev(obs: np.ndarray, pred: np.ndarray) -> float:
    pred = np.clip(pred, 1e-9, None)
    term = np.where(obs > 0, obs * np.log(np.where(obs > 0, obs, 1) / pred), 0.0)
    return float(2 * np.sum(term - (obs - pred)))


# ---------------------------------------------------------------- 1. fans


def fans() -> dict:
    sp, fam = P.genfan()
    t, d = sp["exit_fh"].to_numpy(float), (sp["removal_reason"] == "failure").to_numpy(float)
    b, e = weibull_mle(t, d)
    m = fit_tier_c(sp, fam, hessian=False)
    grid = np.array([2_000, 5_000, 10_000, 20_000, 30_000], float)
    p_mle = 1 - np.exp(-(grid / e) ** b)
    p_tc = _marginal_fail(m, "GEN-FAN", "field", grid)
    return {"units": len(sp), "failures": int(d.sum()),
            "independent_mle": {"beta": round(b, 4), "eta_hours": round(e, 0)},
            "tier_c": {"beta": round(m.params("GEN-FAN", "field")[0], 4),
                       "eta_hours": round(m.params("GEN-FAN", "field")[1], 0), "frailty_k": round(m.frailty_k, 2)},
            "failure_probability_by_hours": {int(h): {"independent_mle": round(float(a), 4), "tier_c": round(float(c), 4)}
                                             for h, a, c in zip(grid, p_mle, p_tc)},
            "max_abs_difference": round(float(np.max(np.abs(p_mle - p_tc))), 4)}


# ---------------------------------------------------------------- 2. drives


NO_POOLING_MIN_FAILURES = 3
METHODS = ("tier_c", "tier_c_part_shape", "complete_pooling", "no_pooling")


def _weibull_scores(t: np.ndarray, beta, eta, k: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(expected failures by t, log hazard at t) per unit; with k, the unit's gamma frailty integrated out."""
    t = np.maximum(np.asarray(t, float), 1e-9)
    with np.errstate(over="ignore"):
        lam = np.minimum((t / eta) ** beta, 1e6)
    logh = np.log(beta) - np.log(eta) + (beta - 1) * np.log(t / eta)
    if k is None:
        return lam, logh
    return k * np.log1p(lam / k), logh - np.log1p(lam / k)


def _drive_predictions(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Per held-out drive: expected failures by its observed time (H) and log hazard there (log h).

    Held-out log-likelihood is d*log h - H; and sum(H) against observed failures is unbiased under censoring,
    which a 'probability of failing by the observed time' is not (a failed drive's time is its failure time)."""
    sp, fam = P.drive_spells(train)
    t = test["time"].to_numpy(float)
    out = {k: (np.empty(len(test)), np.empty(len(test))) for k in METHODS}
    for key, part_shape in (("tier_c", False), ("tier_c_part_shape", True)):
        m = fit_tier_c(sp, fam, hessian=False, part_shape=part_shape)
        m.family_of.update({pn: P.maker(pn) for pn in test["model"].unique()})   # unseen: their maker's typical
        for (pn, env), idx in test.groupby(["model", "env"]).indices.items():
            beta, eta = m.params(pn, env)
            out[key][0][idx], out[key][1][idx] = _weibull_scores(t[idx], beta, eta, m.frailty_k)
    b, e = weibull_mle(train["time"], train["status"])                      # complete pooling: one Weibull for all
    out["complete_pooling"][0][:], out["complete_pooling"][1][:] = _weibull_scores(t, b, e)
    # no pooling: a separate fit per model, where it has at least 3 failures to fit (else the pooled fit);
    # with fewer, a per-model maximum-likelihood fit is degenerate
    fits = {pn: weibull_mle(g["time"], g["status"]) for pn, g in train.groupby("model")
            if g["status"].sum() >= NO_POOLING_MIN_FAILURES}
    for pn, idx in test.groupby("model").indices.items():
        bb, ee = fits.get(pn, (b, e))
        out["no_pooling"][0][idx], out["no_pooling"][1][idx] = _weibull_scores(t[idx], bb, ee)
    return {**out, "y": test["status"].to_numpy(float), "model": m}


def drives(seeds=(0, 1, 2), train_share: float = 0.5, sample: float = 1.0) -> dict:
    d = P.drives()
    out = {"drives": len(d), "models": int(d["model"].nunique()), "failures": int(d["status"].sum()),
           "train_share": train_share, "training_sample": sample, "runs": []}
    methods = METHODS
    for s in seeds:
        rng = np.random.default_rng(s)
        is_train = rng.random(len(d)) < train_share
        train, test = d[is_train], d[~is_train].reset_index(drop=True)
        if sample < 1.0:
            train = train[rng.random(len(train)) < sample]
        t0 = time.time()
        pr = _drive_predictions(train, test)
        y = pr["y"]
        n_train_fail = train.groupby("model")["status"].sum()
        sparse = test["model"].map(n_train_fail).fillna(0).to_numpy() <= 5
        run = {"seed": s, "fit_seconds": round(time.time() - t0, 1), "train_drives": len(train),
               "sparse_models_test_drives": int(sparse.sum()), "sparse_models_test_failures": int(y[sparse].sum())}
        for k in methods:
            H, logh = pr[k]
            ll = y * logh - H
            by = pd.DataFrame({"m": test["model"], "H": H, "y": y})
            g_all, g_sp = by.groupby("m").sum(), by[sparse].groupby("m").sum()
            run[k] = {"loglik_per_1000": round(1000 * float(ll.mean()), 2),
                      "loglik_per_1000_sparse": round(1000 * float(ll[sparse].mean()), 2),
                      "deviance_by_model": round(_poisson_dev(g_all["y"].to_numpy(), g_all["H"].to_numpy()), 1),
                      "deviance_by_model_sparse": round(_poisson_dev(g_sp["y"].to_numpy(), g_sp["H"].to_numpy()), 1),
                      "expected_vs_observed": [round(float(H.sum()), 1), int(y.sum())]}
        out["runs"].append(run)
        m = pr["model"]
    out["temperature_effect"] = {f"{f} {e}": round(float(np.exp(m.gamma[i])), 2) for (f, e), i in m._fe.items()}
    keys = ("loglik_per_1000", "loglik_per_1000_sparse", "deviance_by_model", "deviance_by_model_sparse")
    out["mean"] = {k: {s: round(float(np.mean([r[k][s] for r in out["runs"]])), 2) for s in keys} for k in methods}
    return out


# ---------------------------------------------------------------- 3. valve seats


def _simulate_counts(model: TierCModel, v0: float, x0: float, horizon: float, z: np.ndarray,
                     rng: np.random.Generator) -> np.ndarray:
    """Replacements in the next ``horizon`` days for an engine with virtual age v0 and x0 days since its
    last replacement, one draw per frailty value in z (Kijima type I with the shop's q)."""
    beta, eta = model.params("VALVE-SEAT", "field")
    q = model.q_hat.get("SHOP", model.default_q)
    counts = np.zeros(len(z))
    for j, zj in enumerate(z):
        v, x, left, n = v0, x0, horizon, 0
        while True:
            a = v + x
            u = rng.random()
            total = eta * ((a / eta) ** beta - math.log(u) / zj) ** (1 / beta)
            dt = total - a
            if dt > left:
                break
            left -= dt
            n += 1
            v, x = v + q * (x + dt), 0.0
        counts[j] = n
    return counts


def valve_seats(cutoffs=(300.0, 400.0, 500.0), draws: int = 2000, seed: int = 0) -> dict:
    hist = P.valve_seats()
    end = hist.groupby("engine")["day"].max()
    rng = np.random.default_rng(seed)
    rows, fits = [], {}
    for T in cutoffs:
        sp, fam = P.valve_seat_spells(hist, cutoff=T)
        m = fit_tier_c(sp, fam, hessian=False)
        beta, eta = m.params("VALVE-SEAT", "field")
        q, k = m.q_hat.get("SHOP", m.default_q), m.frailty_k
        fits[T] = {"beta": round(beta, 3), "eta_days": round(eta, 1), "shop_q": round(q, 3), "frailty_k": round(k, 2)}
        before = hist[(hist["replaced"] == 1) & (hist["day"] <= T)]
        exposure = sum(min(T, end[e]) for e in end.index)
        hpp = len(before) / exposure
        for eng in end.index:
            if end[eng] <= T:
                continue
            ev = before[before["engine"] == eng]["day"].to_numpy()
            # virtual age and own cumulative hazard up to T (for the unit's frailty posterior)
            v, prev, lam = 0.0, 0.0, 0.0
            for tday in ev:
                x = tday - prev
                lam += (((v + x) / eta) ** beta - (v / eta) ** beta)
                v, prev = v + q * x, tday
            x_now = T - prev
            lam += (((v + x_now) / eta) ** beta - (v / eta) ** beta)
            n_i = len(ev)
            z_post = rng.gamma(k + n_i, 1 / (k + lam), draws)
            z_pop = rng.gamma(k, 1 / k, draws)
            obs = int(((hist["engine"] == eng) & (hist["replaced"] == 1) & (hist["day"] > T)).sum())
            h = end[eng] - T
            rows.append({"cutoff": T, "engine": int(eng), "observed": obs, "horizon": h,
                         "tier_c_unit": float(_simulate_counts(m, v, x_now, h, z_post, rng).mean()),
                         "tier_c_population": float(_simulate_counts(m, v, x_now, h, z_pop, rng).mean()),
                         "constant_rate": hpp * h, "own_rate": n_i / T * h})
    df = pd.DataFrame(rows)
    methods = ("tier_c_unit", "tier_c_population", "constant_rate", "own_rate")
    by_cut = {}
    for T, g in df.groupby("cutoff"):
        by_cut[str(int(T))] = {"engines": len(g), "observed": int(g["observed"].sum()),
                               **{mm: {"predicted": round(float(g[mm].sum()), 1),
                                       "deviance": round(_poisson_dev(g["observed"].to_numpy(), g[mm].to_numpy()), 2),
                                       "mae": round(float(np.abs(g[mm] - g["observed"]).mean()), 3)}
                                  for mm in methods}}
    total = {mm: {"deviance": round(_poisson_dev(df["observed"].to_numpy(), df[mm].to_numpy()), 2),
                  "mae": round(float(np.abs(df[mm] - df["observed"]).mean()), 3)} for mm in methods}
    return {"engines": int(len(end)), "replacements": int(hist["replaced"].sum()), "fits": fits,
            "by_cutoff": by_cut, "total": total}


# ---------------------------------------------------------------- 4. braking grids


def braking_grids() -> dict:
    sp, fam = P.braking_grids()
    m = fit_tier_c(sp, fam)
    i1, i2 = m._pn["GRID-BATCH1"], m._pn["GRID-BATCH2"]
    o = m._offset("log_eta")
    diff = m.log_eta_p[i2] - m.log_eta_p[i1]
    var = m.cov[o + i1, o + i1] + m.cov[o + i2, o + i2] - 2 * m.cov[o + i1, o + i2]
    se = math.sqrt(max(var, 0.0))
    ratio = [math.exp(diff - 1.645 * se), math.exp(diff), math.exp(diff + 1.645 * se)]
    per = {}
    for pn in ("GRID-BATCH1", "GRID-BATCH2"):
        g = sp[sp["pn"] == pn]
        per[pn] = {"grids": len(g), "replacements": int((g["removal_reason"] == "failure").sum()),
                   "locomotives": int(g["serial"].nunique()),
                   "eta_days": round(m.params(pn, "field")[1], 0),
                   "replacements_per_1000_days": round(1000 * (g["removal_reason"] == "failure").sum()
                                                       / g["exit_fh"].sum(), 2)}
    return {"batches": per, "beta": round(m.params("GRID-BATCH1", "field")[0], 3),
            "batch2_life_vs_batch1_90ci": [round(x, 3) for x in ratio],
            "batch2_shorter_with_90pct_confidence": ratio[2] < 1.0}


def run_all(log=print) -> dict:
    out = {}
    for name, fn in (("fans", fans), ("braking_grids", braking_grids), ("valve_seats", valve_seats),
                     ("drives", drives), ("drives_sparse_10pct", lambda: drives(sample=0.1))):
        t0 = time.time()
        out[name] = fn()
        log(f"  {name}: {time.time() - t0:.0f} s")
    return out
