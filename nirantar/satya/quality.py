"""SATYA: data truth engine (invariants, data-quality scores, Evidence Grades).

Physical-world invariants that maintenance records must obey, checked on the
spell (installation) and repair tables. Each violation is reported with a
code so stewards can fix it, and data quality is scored per part number.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MAX_FH_PER_DAY = 4.0

ISSUE_WEIGHTS = {
    "NEG_INTERVAL": 1.0,          # exit FH < entry FH
    "BACKDATED_REMOVAL": 1.0,     # removal before installation
    "DOUBLE_INSTALL": 1.0,        # same serial on two aircraft at once
    "INSTALLED_AT_AGENCY": 1.0,   # serial flying while booked in at a repair agency
    "MISSING_REPAIR": 0.5,        # failure removal without any later repair record
    "DUPLICATE_SPELL": 0.5,
    "IMPLAUSIBLE_FH": 0.8,        # more flight hours than the calendar allows
    "MISSING_KEY": 1.0,
    "REPAIR_TIME_ORDER": 1.0,     # repair done before started / started before sent
    "DUPLICATE_REPAIR": 0.5,
}


def check_spells(spells: pd.DataFrame, repairs: pd.DataFrame, horizon_day: float | None = None,
                 repair_grace_days: float = 150.0) -> pd.DataFrame:
    """Return one row per (record, issue)."""
    issues: list[dict] = []
    sp = spells.reset_index().rename(columns={"index": "row"})

    def add(rows: pd.DataFrame, code: str, table: str = "spells"):
        for r in rows.itertuples(index=False):
            issues.append({"table": table, "row": int(r.row), "serial": getattr(r, "serial", None),
                           "pn": getattr(r, "pn", None), "issue": code})

    add(sp[sp["serial"].isna() | sp["pn"].isna()], "MISSING_KEY")
    add(sp[sp["exit_fh"] < sp["entry_fh"]], "NEG_INTERVAL")
    has_rem = sp["removal_day"].notna()
    add(sp[has_rem & (sp["removal_day"] < sp["install_day"])], "BACKDATED_REMOVAL")
    dup = sp.duplicated(subset=["serial", "tail", "install_day", "removal_day"], keep="first")
    add(sp[dup], "DUPLICATE_SPELL")

    end = horizon_day if horizon_day is not None else float(np.nanmax(sp[["install_day", "removal_day"]].to_numpy()))
    days = (sp["removal_day"].fillna(end) - sp["install_day"])
    ok_days = days > 0
    add(sp[ok_days & ((sp["exit_fh"] - sp["entry_fh"]) / days.where(ok_days, 1.0) > MAX_FH_PER_DAY + 1e-9)],
        "IMPLAUSIBLE_FH")

    # overlapping installations of the same serial
    s2 = sp[~dup].assign(_end=sp["removal_day"].fillna(np.inf)).sort_values(["serial", "install_day"])
    prev_end = s2.groupby("serial")["_end"].shift(1)
    prev_row = s2.groupby("serial")["row"].shift(1)
    clash = prev_end.notna() & (s2["install_day"] < prev_end - 1e-9)
    add(s2[clash], "DOUBLE_INSTALL")
    add(sp[sp["row"].isin(prev_row[clash].astype(int))], "DOUBLE_INSTALL")      # the other half

    if len(repairs):
        rp = repairs.reset_index().rename(columns={"index": "row"})
        bad = (rp["done_day"] < rp["start_day"]) | (rp["start_day"] < rp["sent_day"])      # NaN = in progress
        add(rp[bad], "REPAIR_TIME_ORDER", "repairs")
        add(rp[rp.duplicated(subset=["serial", "sent_day", "agency"], keep="first")], "DUPLICATE_REPAIR", "repairs")

        # flying while at an agency
        m = sp.merge(rp[["serial", "sent_day", "done_day"]], on="serial", how="inner")
        inside = (m["install_day"] > m["sent_day"] + 1e-9) & (m["install_day"] < m["done_day"].fillna(np.inf) - 1e-9)
        add(m[inside].drop_duplicates("row"), "INSTALLED_AT_AGENCY")

        # failure removals with no subsequent repair record
        fails = sp[(sp["removal_reason"] == "failure") & has_rem & (sp["removal_day"] < end - repair_grace_days)]
        later = fails.merge(rp[["serial", "sent_day"]], on="serial", how="left")
        later = later[later["sent_day"].isna() | (later["sent_day"] >= later["removal_day"] - 1e-9)]
        has_repair = later.dropna(subset=["sent_day"])["row"].unique()
        add(fails[~fails["row"].isin(has_repair)], "MISSING_REPAIR")

    return pd.DataFrame(issues, columns=["table", "row", "serial", "pn", "issue"])


def dq_scores(spells: pd.DataFrame, issues: pd.DataFrame) -> pd.DataFrame:
    """Data-quality score per part number: 1 - weighted issue rate (floored at 0)."""
    n = spells.groupby("pn").size().rename("records")
    if issues.empty:
        out = n.to_frame()
        out["weighted_issues"] = 0.0
    else:
        iss = issues[issues["table"] == "spells"].copy()
        iss["w"] = iss["issue"].map(ISSUE_WEIGHTS).fillna(1.0)
        w = iss.groupby("pn")["w"].sum().rename("weighted_issues")
        out = n.to_frame().join(w, how="left").fillna({"weighted_issues": 0.0})
    out["dq"] = (1.0 - out["weighted_issues"] / out["records"]).clip(lower=0.0).round(3)
    return out.reset_index()


def clean(spells: pd.DataFrame, issues: pd.DataFrame,
          drop_codes: tuple[str, ...] = ("NEG_INTERVAL", "BACKDATED_REMOVAL", "DUPLICATE_SPELL",
                                         "IMPLAUSIBLE_FH", "DOUBLE_INSTALL", "MISSING_KEY")) -> pd.DataFrame:
    """Quarantine records with hard violations (they go to the Data Debt Ledger)."""
    bad = issues[(issues["table"] == "spells") & issues["issue"].isin(drop_codes)]["row"].unique()
    return spells.drop(index=bad, errors="ignore")


# ---------------------------------------------------------------- defect injection (for testing)


def inject_defects(spells: pd.DataFrame, rate: float = 0.04, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corrupt a copy of the records with known defects.

    Returns (corrupted, truth); ``truth.row`` is the row in the corrupted frame
    that carries the defect (for duplicates, the appended copy).
    """
    rng = np.random.default_rng(seed)
    df = spells.copy().reset_index(drop=True)
    truth = []
    n = len(df)
    k = max(1, int(rate * n))

    idx = rng.choice(n, size=k, replace=False)
    kinds = rng.choice(["BACKDATED_REMOVAL", "IMPLAUSIBLE_FH", "WRONG_SERIAL", "DUPLICATE_SPELL"], size=k)
    extra = []
    for i, kind in zip(idx, kinds):
        if kind == "BACKDATED_REMOVAL" and pd.notna(df.at[i, "removal_day"]):
            df.at[i, "removal_day"] = df.at[i, "install_day"] - rng.uniform(1, 30)
        elif kind == "IMPLAUSIBLE_FH":
            df.at[i, "exit_fh"] = df.at[i, "entry_fh"] + (df.at[i, "exit_fh"] - df.at[i, "entry_fh"]) * 20 + 500
        elif kind == "WRONG_SERIAL":
            same = df.index[(df["pn"] == df.at[i, "pn"]) & (df["serial"] != df.at[i, "serial"])]
            if len(same):
                df.at[i, "serial"] = df.at[int(rng.choice(same)), "serial"]
        elif kind == "DUPLICATE_SPELL":
            extra.append(df.loc[i].copy())
            truth.append({"row": n + len(extra) - 1, "defect": kind})
            continue
        else:
            continue
        truth.append({"row": int(i), "defect": kind})
    if extra:
        df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    return df, pd.DataFrame(truth)


# ---------------------------------------------------------------- Evidence Grades


@dataclass(frozen=True)
class Evidence:
    grade: str
    reasons: tuple[str, ...]


def evidence_grade(dq: float, n_events: int, calibration_error_pts: float | None = None,
                   out_of_distribution: bool = False, model_disagreement: float = 0.0) -> Evidence:
    """E1 (decision-grade) ... E5 (insufficient). Thresholds follow Document 3, section 10.1."""
    reasons = []
    cal = calibration_error_pts if calibration_error_pts is not None else 5.0
    if dq < 0.5 or model_disagreement > 0.5:
        return Evidence("E5", ("data quality < 0.5" if dq < 0.5 else "models disagree",))
    if out_of_distribution:
        reasons.append("out-of-distribution input")
    if dq >= 0.9 and cal <= 5 and n_events >= 50 and not out_of_distribution and model_disagreement <= 0.1:
        return Evidence("E1", ("dq>=0.9", "calibrated", "ESS>=50"))
    if dq >= 0.8 and cal <= 8 and n_events >= 20 and not out_of_distribution:
        return Evidence("E2", ("dq>=0.8", "ESS>=20"))
    if dq >= 0.65 and n_events >= 8:
        return Evidence("E3", tuple(reasons) or ("dq>=0.65", "ESS>=8"))
    return Evidence("E4", tuple(reasons) or ("small sample or weak data",))
