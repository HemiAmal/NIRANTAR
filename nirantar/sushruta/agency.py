"""SUSHRUTA: repair-agency effectiveness, rogue serials, effectiveness-aware routing.

Agency repair effectiveness q (Kijima virtual age) comes from the Tier C fit.

Rogue units: each serial has n failures over an expected cumulative hazard
Lambda (from the fitted fleet model). A two-class mixture, normal units
(z = 1) versus rogues (z = z_r) with prior share pi, is fitted by EM across
serials. The posterior rogue probability of a serial is

    p = pi * LR / (pi * LR + 1 - pi),   LR = z_r^n * exp(-(z_r - 1) * Lambda)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nirantar.dhanvantari.tier_c import TierCModel, build_design


def serial_frailty(model: TierCModel, spells: pd.DataFrame, family_of: dict[str, str],
                   z_threshold: float = 1.5) -> pd.DataFrame:
    """Posterior probability that each serial is a rogue (two-class EM mixture)."""
    d = build_design(spells, family_of)
    q = np.array([model.q_hat[a] for a in d.agencies])
    V = d.M @ q
    pn_names = np.array(d.pns)[d.pn_idx]
    df = spells.copy()          # same filter and order as build_design
    df = df[np.isfinite(df["exit_fh"]) & (df["exit_fh"] > df["entry_fh"])]
    df = df.sort_values(["serial", "install_day"]).reset_index(drop=True)
    lam = np.empty(len(df))
    for j, (pn, env) in enumerate(zip(pn_names, df["env"])):
        lam[j] = model.cum_hazard(pn, env, V[j] + d.entry[j], V[j] + d.exit[j])
    out = pd.DataFrame({"serial": d.serial, "pn": pn_names, "lam": lam, "fail": d.event})
    agg = out.groupby(["serial", "pn"], as_index=False).agg(n_fail=("fail", "sum"), lam=("lam", "sum"))
    # scale so the bulk of units sits at z = 1 (the fit absorbs mean frailty into eta)
    scale = agg["n_fail"].sum() / max(agg["lam"].sum(), 1e-9)
    n = agg["n_fail"].to_numpy(float)
    lam = agg["lam"].to_numpy(float) * scale
    pi, zr = 0.05, 3.0
    for _ in range(200):
        log_lr = n * np.log(zr) - (zr - 1.0) * lam
        p = 1.0 / (1.0 + np.exp(-(np.log(pi) - np.log1p(-pi) + log_lr)))
        pi_new = float(np.clip(p.mean(), 1e-4, 0.5))
        zr_new = float(max((p * n).sum() / max((p * lam).sum(), 1e-9), z_threshold))
        if abs(pi_new - pi) < 1e-7 and abs(zr_new - zr) < 1e-6:
            break
        pi, zr = pi_new, zr_new
    agg["lam_scaled"] = lam
    agg["p_rogue"] = p
    agg.attrs["mixture"] = {"pi": pi, "z_rogue": zr}
    return agg.sort_values("p_rogue", ascending=False).reset_index(drop=True)


def flag_rogues(frailty: pd.DataFrame, p_min: float = 0.8, min_failures: int = 2) -> set[int]:
    sel = frailty[(frailty["p_rogue"] >= p_min) & (frailty["n_fail"] >= min_failures)]
    return set(int(s) for s in sel["serial"])


def agency_scorecards(model: TierCModel, repairs: pd.DataFrame, level: float = 0.9) -> pd.DataFrame:
    """Turnaround and repair-quality scorecard per agency (with uncertainty)."""
    rows = []
    for a in model.agencies:
        q, lo, hi = model.q_interval(a, level)
        r = repairs[repairs["agency"] == a] if len(repairs) else repairs
        tat = (r["done_day"] - r["start_day"]) if len(r) else pd.Series(dtype=float)
        pipe = (r["done_day"] - r["sent_day"]) if len(r) else pd.Series(dtype=float)
        rows.append({
            "agency": a, "jobs": int(len(r)),
            "q_hat": round(q, 3), "q_lo": round(lo, 3), "q_hi": round(hi, 3),
            "tat_median_days": round(float(tat.median()), 1) if len(tat) else None,
            "tat_p90_days": round(float(tat.quantile(0.9)), 1) if len(tat) else None,
            "send_to_done_median_days": round(float(pipe.median()), 1) if len(pipe) else None,
        })
    return pd.DataFrame(rows).sort_values("q_hat").reset_index(drop=True)
