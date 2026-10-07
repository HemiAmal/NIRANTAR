"""Planning world and fleet state, rebuilt from records alone.

A real deployment never sees the simulator's hidden truth. Everything the twin
needs is estimated here from the SETU store:

* **Part reliability** (Weibull shape and scale per part number, shrunk towards
  its system's, environment effects) and **repair quality** per agency:
  DHANVANTARI's fit, with the specification chosen by the last ``refit``.
* **Each unit's own failure tendency**: the gamma-frailty posterior mean
  ``(k + failures) / (k + expected failures)`` from the same fit, so a unit
  that keeps failing is planned as one.
* **Repair turnaround** (median and spread), **shipping legs** and **depot
  capacity** per agency: from repair orders and stores receipts.
* **Failure-mode mix** per system: from defect reports.
* **Today's supply regime** per supplier: from how much recent shipping is
  stretched relative to normal; the regime model itself (levels and how
  they change) is a planning assumption kept as master data.

The fleet state at the store's "as of" time comes from the same records:
what is fitted where, what is on the shelf, what is in the repair pipeline
and how long each unit has been there, and how long each aircraft has
waited for a part.

Two gaps are explicit: inspections are not recorded yet (their timing is
spread evenly across the interval), and new purchase orders in flight are
not recorded yet (none are assumed).
"""
from __future__ import annotations

import json
import math
import zlib
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nirantar.bharat_fleet.world import Agency, Base, FleetType, PartNumber, RegimeModel, Serial, World
from nirantar.dhanvantari.tier_c import TierCModel, build_design, fit_tier_c
from nirantar.drishti.signals import disproportionality, exposure_rates
from nirantar.satya.quality import check_spells, dq_scores
from nirantar.setu.schema import Store
from nirantar.sushruta.agency import flag_rogues, serial_frailty


@dataclass
class Estimated:
    world: World
    start: dict
    model: TierCModel
    serial_of: dict[int, str]          # planning id -> serial number as recorded
    id_of: dict[str, int]
    now: float                         # store "as of", days since epoch
    notes: list[str]
    agency_stats: pd.DataFrame
    frames: dict                       # the store's frames with serials as planning ids
    frailty: pd.DataFrame              # per-unit rogue probability (SUSHRUTA)
    signals: pd.DataFrame              # failure-mode signals per system and environment (DRISHTI)
    dq: dict                           # data-quality score per part number (SATYA)


# ---------------------------------------------------------------- helpers


def _hash01(*keys) -> float:
    return (zlib.crc32("|".join(map(str, keys)).encode()) % 10_000) / 10_000.0


def _lognormal_remaining(median: float, sigma: float, elapsed: float) -> float:
    """E[T - e | T > e] for T ~ lognormal(log median, sigma)."""
    if elapsed <= 0:
        return median * math.exp(sigma ** 2 / 2)
    from scipy.stats import lognorm
    dist = lognorm(s=max(sigma, 1e-3), scale=median)
    surv = dist.sf(elapsed)
    if surv < 1e-6:
        return max(1.0, 0.1 * median)
    xs = np.linspace(elapsed, dist.ppf(0.9999) + elapsed, 400)
    return float(np.trapezoid(dist.sf(xs), xs) / surv)


# ---------------------------------------------------------------- agencies


def agency_stats(rep: pd.DataFrame, receipts: pd.DataFrame, agencies: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rec = receipts.sort_values("day")
    rec_by_serial = {s: g["day"].to_numpy() for s, g in rec.groupby("serial")}
    for a in agencies.itertuples():
        r = rep[rep["agency"] == a.agency]
        plain = r[~r["overhaul"].astype(bool)].dropna(subset=["start_day", "done_day"])
        tat = (plain["done_day"] - plain["start_day"]).clip(lower=0.01)
        out_leg = (r["start_day"] - r["sent_day"]).dropna()
        back = []
        for s, d in zip(r["serial"], r["done_day"]):
            if d != d:
                continue
            days = rec_by_serial.get(s)
            if days is not None:
                after = days[days >= d - 1e-6]
                if len(after):
                    back.append(after[0] - d)
        # peak concurrent repairs observed (a lower bound on capacity)
        ev = sorted([(t, 1) for t in r["start_day"].dropna()] + [(t, -1) for t in r["done_day"].dropna()])
        peak = cur = 0
        for _, k in ev:
            cur += k
            peak = max(peak, cur)
        rows.append({
            "agency": a.agency, "country": a.country, "jobs": len(r),
            "tat_median": float(np.exp(np.log(tat).mean())) if len(tat) else 30.0,
            "tat_sigma": float(np.log(tat).std(ddof=1)) if len(tat) > 2 else 0.3,
            "out_leg_base": float(np.quantile(out_leg, 0.2)) if len(out_leg) else 3.0,
            "back_leg_base": float(np.quantile(back, 0.2)) if back else 3.0,
            "peak_concurrent": int(peak),
            "servers": max(1, int(math.ceil(peak * 1.2)) + 1),
        })
    return pd.DataFrame(rows)


def regime_filter(rep: pd.DataFrame, receipts: pd.DataFrame, stats: pd.DataFrame, risk: dict, now: float,
                  tol: float = 0.15, eps: float = 1e-3, queue_p: float = 0.1) -> dict[str, list[float]]:
    """Probability of each supply regime today, per supplier country (hidden-Markov forward filter).

    Shipping time is the agency's normal leg times the regime's multiplier on the day a unit
    leaves, so the records carry three kinds of evidence:

    * a completed return leg (repair finished -> received at base) reveals the multiplier;
    * a repaired unit not yet received has been travelling at least that long (a lower bound);
    * an outbound leg (sent -> repair started) also holds queueing, so it is an upper bound;
    * a unit sent but not started has been travelling at least that long, unless it is queueing
      at the agency (soft evidence, weighted by ``queue_p``).

    The regime model's daily transitions carry the belief from day to day up to today.
    """
    st = stats.set_index("agency")
    rec = receipts.sort_values("day")
    rec_by_serial = {s: g["day"].to_numpy() for s, g in rec.groupby("serial")}
    out = {}
    for c, m in risk.items():
        mult = np.array(m["multipliers"], dtype=float)
        k = len(mult)
        if k < 2:
            out[c] = [1.0]
            continue
        T = np.array(m["transition"], dtype=float)
        days = int(math.floor(now)) + 1
        loglik = np.zeros((days, k))
        ags = [a for a in st.index if st.loc[a, "country"] == c]
        for r in rep[rep["agency"].isin(ags)].itertuples():
            base_back, base_out = st.loc[r.agency, "back_leg_base"], st.loc[r.agency, "out_leg_base"]
            if r.done_day == r.done_day and 0 <= r.done_day <= now:
                d = int(r.done_day)
                arr = rec_by_serial.get(r.serial)
                after = arr[arr >= r.done_day - 1e-6] if arr is not None else []
                if len(after):                                # observed leg: the multiplier itself
                    ratio = (after[0] - r.done_day) / max(base_back, 0.1)
                    loglik[d] += np.where(np.abs(np.log(max(ratio, 1e-3)) - np.log(mult)) < tol, 0.0, np.log(eps))
                else:                                         # still travelling: leg longer than elapsed
                    ratio = (now - r.done_day) / max(base_back, 0.1)
                    loglik[d] += np.where(mult >= ratio * (1 - tol), 0.0, np.log(eps))
            if r.sent_day == r.sent_day and 0 <= r.sent_day <= now:
                d = int(r.sent_day)
                if r.start_day == r.start_day:               # leg + queueing: an upper bound
                    ratio = (r.start_day - r.sent_day) / max(base_out, 0.1)
                    loglik[d] += np.where(mult <= ratio * (1 + tol), 0.0, np.log(eps))
                else:                                         # not started yet: on the way this long, or
                    ratio = (now - r.sent_day) / max(base_out, 0.1)   # queueing at the agency (soft evidence)
                    loglik[d] += np.where(mult >= ratio * (1 - tol), 0.0, np.log(queue_p))
        # stationary start, then predict-update day by day
        w, v = np.linalg.eig(T.T)
        pi = np.real(v[:, np.argmin(np.abs(w - 1))])
        p = np.abs(pi) / np.abs(pi).sum()
        for d in range(days):
            if d:
                p = p @ T
            p = p * np.exp(loglik[d] - loglik[d].max())
            p = p / p.sum()
        out[c] = [round(float(x), 4) for x in p]
    return out


# ---------------------------------------------------------------- main


def estimate(store: Store, model: TierCModel | None = None, rogue_p: float = 0.5) -> Estimated:
    """Planning world and today's fleet state from the store. Units with a rogue probability of at
    least ``rogue_p`` (and two or more failures) are listed as suspected rogues."""
    fr, ms = store.frames(), store.masters()
    now = store.now_day()
    notes = ["Inspections are not recorded yet: each aircraft's inspection timing is spread evenly over its interval.",
             "Purchase orders in flight are not recorded yet: none are assumed."]
    parts = ms["parts"].set_index("pn")
    family_of = parts["family"].to_dict()
    sp, rep = fr["spells"], fr["repairs"]
    if model is None:
        spec = json.loads(store.meta("model_spec") or "{}")
        model = fit_tier_c(sp, family_of, part_shape=spec.get("part_shape", True))

    # serial numbers -> dense planning ids
    serials = sorted(set(sp["serial"]) | set(rep["serial"]) | set(fr["onhand"]["serial"]) | set(fr["receipts"]["serial"]))
    id_of = {s: i for i, s in enumerate(serials)}
    pn_of_serial: dict[str, str] = {}
    for df in (sp, rep, fr["onhand"], fr["receipts"]):
        pn_of_serial.update(dict(zip(df["serial"], df["pn"])))

    # unit frailty posterior (gamma-Poisson), from the same design the fit used
    z_post = _frailty_posterior(model, sp, family_of)
    # the same records keyed by planning id, for everything downstream
    ids = {k: _with_ids(v, id_of) for k, v in fr.items()}
    frailty = serial_frailty(model, ids["spells"], family_of)
    model.rogue_flags = flag_rogues(frailty, p_min=rogue_p)
    signals = disproportionality(ids["snags"].dropna(subset=["mode"]),
                                 exposure=exposure_rates(ids["spells"], family_of))
    dq = dq_scores(ids["spells"], check_spells(ids["spells"], ids["repairs"], horizon_day=now))
    dq = dq.set_index("pn")["dq"].to_dict() if len(dq) else {}

    # masters
    bases_df, fleets_df, air = ms["bases"], ms["fleets"], ms["aircraft"]
    fleets_at = air.groupby("base")["fleet"].apply(lambda x: tuple(sorted(set(x)))).to_dict()
    bases = {b.base: Base(b.base, b.env, fleets_at.get(b.base, ())) for b in bases_df.itertuples()}
    per_base = air.groupby(["fleet", "base"]).size()
    fleets = {f.fleet: FleetType(f.fleet, f.role, int(f.squadron_ue), f.fh_per_day, f.inspection_interval_fh,
                                 f.inspection_days, f.mttr_fail_days, f.mttr_swap_days,
                                 {b: int(n) for (fl, b), n in per_base.items() if fl == f.fleet}, f.role_weight)
              for f in fleets_df.itertuples()}
    pns = {}
    for pn, p in parts.iterrows():
        fam = p["family"]
        beta = model.params(pn, "")[0] if fam in model._fam else 1.5
        eta = float(np.exp(model.log_eta_p[model._pn[pn]])) if pn in model._pn else \
            float(np.exp(model.mu_f[model._fam[fam]])) if fam in model._fam else 400.0
        pns[pn] = PartNumber(pn, p["name"], fam, p["fleet"], p["origin"], beta, eta, int(p["positions"]),
                             tuple(p["eligible_agencies"]), p["default_agency"], float(p["unit_cost_lakh"]),
                             float(p["procurement_days"]))
    env_effect = {fe: float(np.exp(model.gamma[i])) for fe, i in model._fe.items()}
    stats = agency_stats(rep, fr["receipts"], ms["agencies"])
    st = stats.set_index("agency")
    agencies = {a.agency: Agency(a.agency, a.kind or "", a.country, float(model.q_hat.get(a.agency, model.default_q)),
                                 float(st.loc[a.agency, "tat_median"]), float(st.loc[a.agency, "tat_sigma"]),
                                 int(st.loc[a.agency, "servers"]),
                                 float((st.loc[a.agency, "out_leg_base"] + st.loc[a.agency, "back_leg_base"]) / 2))
                for a in ms["agencies"].itertuples()}
    risk = json.loads(store.meta("supply_risk") or "null") or {}
    if not risk:
        notes.append("No supplier risk model in the master data: every supplier assumed normal.")
        risk = {c: {"states": ["normal"], "multipliers": [1.0], "transition": [[1.0]]}
                for c in set(ms["agencies"]["country"]) | set(parts["origin"])}
    regimes = {c: RegimeModel(c, tuple(m["states"]), tuple(m["multipliers"]), tuple(tuple(r) for r in m["transition"]))
               for c, m in risk.items()}
    snags = fr["snags"].dropna(subset=["mode"])
    modes = {fam: (g["mode"].value_counts(normalize=True).to_dict()) for fam, g in snags.groupby("family")}
    for fam in set(parts["family"]):
        modes.setdefault(fam, {"unspecified": 1.0})
    world = World(
        seed=0, fleets=fleets, bases=bases, pns=pns, agencies=agencies, regimes=regimes, env_effect=env_effect,
        failure_modes=modes, env_mode_boost={},
        tails=[{"id": t.tail, "fleet": t.fleet, "base": t.base} for t in air.itertuples()],
        serials=[Serial(i, pn_of_serial[s], float(z_post.get(s, 1.0)), "") for i, s in enumerate(serials)],
        initial_install={}, initial_tso_fh={}, initial_stock={},
        rogue_serials=set(model.rogue_flags), serial_names={i: s for s, i in id_of.items()})

    probs = regime_filter(rep, fr["receipts"], stats, risk, now)
    regimes_now = {c: int(np.argmax(p)) for c, p in probs.items()}
    start = _state(world, model, fr, id_of, stats, risk, regimes_now, now, notes)
    start["regimes"] = regimes_now
    start["regime_probs"] = {c: p for c, p in probs.items() if len(p) > 1}
    return Estimated(world, start, model, {i: s for s, i in id_of.items()}, id_of, now, notes, stats,
                     ids, frailty, signals, dq)


def _with_ids(df: pd.DataFrame, id_of: dict) -> pd.DataFrame:
    if "serial" not in df:
        return df
    df = df.copy()
    df["serial"] = df["serial"].map(id_of).astype("Int64")
    return df


def _frailty_posterior(model: TierCModel, spells: pd.DataFrame, family_of: dict) -> dict[str, float]:
    d = build_design(spells, family_of)
    q = np.array([model.q_hat[a] for a in d.agencies])
    V = d.M @ q
    pn_names = np.array(d.pns)[d.pn_idx]
    df = spells.copy()
    df = df[np.isfinite(df["exit_fh"]) & (df["exit_fh"] > df["entry_fh"])]
    df = df.sort_values(["serial", "install_day"]).reset_index(drop=True)
    lam = np.array([model.cum_hazard(pn, env, V[j] + d.entry[j], V[j] + d.exit[j])
                    for j, (pn, env) in enumerate(zip(pn_names, df["env"]))])
    agg = pd.DataFrame({"serial": d.serial, "lam": lam, "n": d.event}).groupby("serial").sum()
    k = model.frailty_k
    return ((k + agg["n"]) / (k + agg["lam"])).to_dict()


def _state(world: World, model: TierCModel, fr: dict, id_of: dict, stats: pd.DataFrame, risk: dict,
           regimes_now: dict, now: float, notes: list[str]) -> dict:
    n = len(world.serials)
    sp, rep, onhand = fr["spells"], fr["repairs"], fr["onhand"]
    V, X = np.zeros(n), np.zeros(n)
    z = np.array([s.frailty for s in world.serials], dtype=float)
    st = stats.set_index("agency")

    # repair history per unit (estimated virtual age uses the estimated repair quality)
    hist: dict[int, list] = defaultdict(list)
    done = rep.dropna(subset=["done_day"]).sort_values("done_day")
    for r in done.itertuples():
        hist[id_of[r.serial]].append((r.agency, float(r.fh_since_repair or 0.0), "OH" if r.overhaul else "R"))
    for sid, h in hist.items():
        v = 0.0
        for g, x, kind in h:
            v = 0.0 if kind == "OH" else v + model.q_hat.get(g, model.default_q) * x
        V[sid] = v

    # fitted units
    installed: dict[str, dict] = defaultdict(dict)
    open_ = sp[sp["removal_day"].isna()]
    for r in open_.itertuples():
        sid = id_of[r.serial]
        installed[r.tail][(r.pn, int(r.position) - 1)] = sid
        X[sid] = float(r.exit_fh if r.exit_fh == r.exit_fh else r.entry_fh)

    # on the shelf (latest stock-take); hours since repair from the last removal unless repaired since
    stock: dict[tuple, list] = defaultdict(list)
    if not onhand.empty:
        latest = onhand[onhand["day"] == onhand["day"].max()]
        for r in latest.itertuples():
            stock[(r.base, r.pn)].append(id_of[r.serial])
    last_removal = sp.dropna(subset=["removal_day"]).sort_values("removal_day").groupby("serial").last()
    last_done = done.groupby("serial")["done_day"].max()
    fitted = {sid for v in installed.values() for sid in v.values()}
    last_done_d = last_done.to_dict()
    for s, rem_day, exit_fh in zip(last_removal.index, last_removal["removal_day"], last_removal["exit_fh"]):
        sid = id_of[s]
        if sid in fitted:
            continue
        if s in last_done_d and last_done_d[s] >= rem_day:
            X[sid] = 0.0
        else:
            X[sid] = float(exit_fh) if exit_fh == exit_fh else 0.0

    # repair pipeline
    # units in transit: today's estimated supply regime stretches their legs; one overdue is due soon
    mult_now = {c: m["multipliers"][regimes_now.get(c, 0)] for c, m in risk.items()}
    pipeline = []
    in_stock = {sid for v in stock.values() for sid in v}
    rec = fr["receipts"].sort_values("day")
    last_receipt = rec.groupby("serial")["day"].max().to_dict()
    open_rep = rep[rep["done_day"].isna()]
    for k, r in enumerate(open_rep.itertuples()):
        sid = id_of[r.serial]
        a = st.loc[r.agency]
        overhaul = bool(r.overhaul)
        job = {"sid": sid, "pn": r.pn, "agency": r.agency, "from": r.from_base, "sent": float(r.sent_day - now),
               "deep": bool(r.deep_strip), "overhaul": overhaul and not bool(r.deep_strip), "id": 10_000_000 + k}
        if r.start_day == r.start_day:                    # in repair: expected remaining turnaround
            med = a["tat_median"] * (1.5 if overhaul else 1.0)
            pipeline.append({"type": "inrepair", **job,
                             "dt": _lognormal_remaining(med, a["tat_sigma"], now - r.start_day)})
        else:                                             # on its way to the agency, or queued there
            leg = a["out_leg_base"] * mult_now.get(a["country"], 1.0)
            pipeline.append({"type": "job", **job, "dt": max(0.1 * leg, leg - (now - r.sent_day))})
    in_repair_now = set(open_rep["serial"])
    for r in done.itertuples():                           # repaired, not yet received back at base
        sid = id_of[r.serial]
        if sid in in_stock or sid in fitted:
            continue
        if r.serial in last_receipt and last_receipt[r.serial] >= r.done_day - 1e-6:
            continue
        if last_done_d[r.serial] > r.done_day:            # only the unit's latest repair can still be in transit
            continue
        if r.serial in in_repair_now:
            continue
        a = st.loc[r.agency]
        leg = a["back_leg_base"] * mult_now.get(a["country"], 1.0)
        pipeline.append({"type": "arrive", "base": r.from_base, "sid": sid, "pn": r.pn,
                         "dt": max(0.1 * leg, leg - (now - r.done_day))})

    # aircraft waiting for parts: empty slots, waiting since the last removal from that slot
    waiting = []
    last_out = sp.dropna(subset=["removal_day"]).sort_values("removal_day").groupby(["tail", "pn", "position"])["removal_day"].last()
    pns_of = defaultdict(list)
    for p in world.pns.values():
        pns_of[p.fleet].append(p)
    for t in world.tails:
        inst = installed.get(t["id"], {})
        for p in pns_of[t["fleet"]]:
            for k in range(p.positions):
                if (p.pn, k) not in inst:
                    since = last_out.get((t["id"], p.pn, k + 1), now)
                    waiting.append({"tail": t["id"], "pn": p.pn, "pos": k + 1, "days": float(now - since)})

    since_insp = {t["id"]: world.fleets[t["fleet"]].inspection_interval_fh * _hash01("insp", t["id"]) for t in world.tails}
    return {"V": V, "X": X, "z": z, "hist": dict(hist), "installed": dict(installed), "since_insp": since_insp,
            "stock": dict(stock), "pipeline": pipeline, "regimes": {}, "waiting": waiting,
            "work_left": {t["id"]: 0.0 for t in world.tails}, "new_pn": {}}
