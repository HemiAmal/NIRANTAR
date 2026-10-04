"""DRISHTI: airworthiness pharmacovigilance.

Disproportionality statistics borrowed from drug-safety signal detection,
applied to defect (snag) reports. Within each part family, an environment
context is compared against the family's other environments:

             mode    other modes
  context     a          b
  others      c          d

PRR = [a/(a+b)] / [c/(c+d)], ROR = ad/bc, and the BCPNN information component
IC = log2((O + 1/2) / (E + 1/2)) with E = (a+b)(a+c)/n. A signal needs the
lower 95% bound IC025 > 0 (Noren et al. approximation) and at least
``min_count`` reports. A weaker *candidate* tier (PRR lower 95% bound > 1,
IC > 0, at least ``min_count`` reports) surfaces emerging patterns for engineering
review before they are statistically confirmed; small fleets often need pooled
(federated) reports across services to reach the strict tier.

Unlike drug safety, exposure (flight hours) is known. When an ``exposure``
table is given, both tiers also require the mode's *rate* per flight hour in the
context to exceed the rate elsewhere (rate-ratio lower bound > 1 for signals,
rate ratio > 1 for candidates). This removes compositional "mirror" artefacts:
when one mode rises in a context, other modes' shares fall there, but their
rates do not.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def ic_interval(observed: float, expected: float) -> tuple[float, float, float]:
    o = observed + 0.5
    ic = math.log2(o / (expected + 0.5))
    lo = ic - 3.3 * o ** -0.5 - 2.0 * o ** -1.5
    hi = ic + 2.4 * o ** -0.5 - 0.5 * o ** -1.5
    return ic, lo, hi


def disproportionality(snags: pd.DataFrame, context: str = "env", stratum: str = "family",
                       event: str = "mode", min_count: int = 3,
                       exposure: pd.DataFrame | None = None) -> pd.DataFrame:
    """Disproportionality table; ``exposure`` has columns [stratum, context, "fh"]."""
    fh = None
    if exposure is not None:
        fh = {(r[stratum], r[context]): float(r["fh"]) for _, r in exposure.iterrows()}
    rows = []
    for fam, g in snags.groupby(stratum):
        n = len(g)
        if n < 10 or g[context].nunique() < 2:
            continue
        ctab = pd.crosstab(g[context], g[event])
        for ctx in ctab.index:
            for ev in ctab.columns:
                a = float(ctab.loc[ctx, ev])
                row_tot = float(ctab.loc[ctx].sum())
                col_tot = float(ctab[ev].sum())
                b = row_tot - a
                c = col_tot - a
                dd = n - a - b - c
                expected = row_tot * col_tot / n
                ic, ic_lo, ic_hi = ic_interval(a, expected)
                aa, bb, cc, d2 = a + 0.5, b + 0.5, c + 0.5, dd + 0.5
                prr = (aa / (aa + bb)) / (cc / (cc + d2))
                se_prr = math.sqrt(max(1 / aa - 1 / (aa + bb) + 1 / cc - 1 / (cc + d2), 0.0))
                ror = (aa * d2) / (bb * cc)
                se_ror = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / d2)
                rr = rr_lo = None
                if fh is not None:
                    fh_ctx = fh.get((fam, ctx), 0.0)
                    fh_oth = sum(v for (f2, c2), v in fh.items() if f2 == fam and c2 != ctx)
                    if fh_ctx > 0 and fh_oth > 0:
                        rr = (aa / fh_ctx) / (cc / fh_oth)
                        rr_lo = rr * math.exp(-1.96 * math.sqrt(1 / aa + 1 / cc))
                prr_lo = prr * math.exp(-1.96 * se_prr)
                rate_ok_signal = True if fh is None else (rr_lo is not None and rr_lo > 1)
                rate_ok_cand = True if fh is None else (rr is not None and rr > 1)
                rows.append({
                    stratum: fam, context: ctx, event: ev, "n_reports": int(a),
                    "expected": round(expected, 2), "IC": round(ic, 3), "IC025": round(ic_lo, 3),
                    "IC975": round(ic_hi, 3), "PRR": round(prr, 2),
                    "PRR_lo": round(prr * math.exp(-1.96 * se_prr), 2),
                    "ROR": round(ror, 2), "ROR_lo": round(ror * math.exp(-1.96 * se_ror), 2),
                    "rate_ratio": None if rr is None else round(rr, 2),
                    "rate_ratio_lo": None if rr_lo is None else round(rr_lo, 2),
                    "signal": bool(ic_lo > 0 and a >= min_count and rate_ok_signal),
                    "candidate": bool(prr_lo > 1 and ic > 0 and a >= min_count and rate_ok_cand),
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["signal", "candidate", "IC025"], ascending=[False, False, False]).reset_index(drop=True)


def exposure_rates(spells: pd.DataFrame, family_of: dict[str, str]) -> pd.DataFrame:
    """Flight hours, failures and failures per 1,000 FH by family and environment."""
    df = spells.copy()
    df["family"] = df["pn"].map(family_of)
    df["fh"] = (df["exit_fh"].fillna(df["entry_fh"]) - df["entry_fh"]).clip(lower=0)
    df["fail"] = (df["removal_reason"] == "failure").astype(float)
    g = df.groupby(["family", "env"], as_index=False).agg(fh=("fh", "sum"), failures=("fail", "sum"))
    g["per_1000_fh"] = (1000 * g["failures"] / g["fh"].replace(0, np.nan)).round(3)
    return g


def time_to_signal(snags: pd.DataFrame, family: str, env: str, mode: str,
                   step_days: float = 7.0, min_count: int = 3) -> float | None:
    """First day on which (family, env, mode) becomes a signal when reports arrive over time."""
    s = snags.sort_values("day")
    for day in np.arange(step_days, s["day"].max() + step_days, step_days):
        res = disproportionality(s[s["day"] <= day], min_count=min_count)
        if res.empty:
            continue
        hit = res[(res["family"] == family) & (res["env"] == env) & (res["mode"] == mode) & res["signal"]]
        if len(hit):
            return float(day)
    return None
