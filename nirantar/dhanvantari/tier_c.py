"""DHANVANTARI Tier C: records-only reliability with imperfect repair.

Model (per installation spell j of serial i, part number p, family f, env e):

    hazard   h(a) = (beta_f / eta) * (a / eta)^(beta_f - 1)
    eta      = exp(log_eta_p + gamma_{f,e})
    age      a runs from V_j + entry_fh to V_j + exit_fh        (Kijima type I)
    V_j      = sum over earlier cycles since the last overhaul of q_g * X
               where g is the agency that repaired the serial after that cycle

Unknowns: log_eta_p (shrunk towards a family mean), log_beta_f, gamma_{f,e}
(environment effects) and q_g (repair effectiveness per agency, via logit).
A shared gamma frailty z_i ~ Gamma(k, k) per serial absorbs unit-to-unit
heterogeneity (rogue units) and is integrated out analytically:

    L_i = Gamma(k + n_i) / Gamma(k) * k^k * prod(h^d) / (k + Lambda_i)^(k + n_i)

Fitted by MAP with analytic gradients; uncertainty by a Laplace approximation.
Removals other than failures (preventive, still installed) are censored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import digamma, expit, gammaln, logit

PRIOR_LOG_BETA = (math.log(1.5), 0.5)
PRIOR_GAMMA_SD = 0.5
PRIOR_ETA_SD = 0.7
PRIOR_Q = (logit(0.3), 1.5)
PRIOR_LOG_K = (math.log(4.0), 1.0)


@dataclass
class _Design:
    pn_idx: np.ndarray
    fam_idx: np.ndarray
    fe_idx: np.ndarray
    entry: np.ndarray
    exit: np.ndarray
    event: np.ndarray
    M: np.ndarray                 # (n_spells, n_agencies): FH contributions to virtual age
    serial: np.ndarray
    pns: list[str]
    fams: list[str]
    fes: list[tuple[str, str]]
    agencies: list[str]
    fam_of_pn: np.ndarray
    serial_idx: np.ndarray        # dense serial index per spell
    n_serials: int
    n_events_serial: np.ndarray


def build_design(spells: pd.DataFrame, family_of: dict[str, str]) -> _Design:
    """Turn spell records into arrays, including the virtual-age design matrix."""
    df = spells.copy()
    df = df[np.isfinite(df["exit_fh"]) & (df["exit_fh"] > df["entry_fh"])]
    df = df.sort_values(["serial", "install_day"]).reset_index(drop=True)
    df["family"] = df["pn"].map(family_of)

    pns = sorted(df["pn"].unique())
    fams = sorted(df["family"].unique())
    fes = sorted({(f, e) for f, e in zip(df["family"], df["env"])})
    raw_ag = {a.split("#")[0] for a in df["prev_agency"].unique() if a != "UNKNOWN"}
    agencies = sorted(raw_ag)
    ai = {a: k for k, a in enumerate(agencies)}

    n = len(df)
    M = np.zeros((n, len(agencies)))
    contrib = np.zeros(len(agencies))
    prev_serial = None
    prev_exit = 0.0
    for j, row in enumerate(df.itertuples(index=False)):
        if row.serial != prev_serial:
            contrib[:] = 0.0
        else:
            g = row.prev_agency
            if g.endswith("#OH") or g == "UNKNOWN":
                contrib[:] = 0.0
            else:
                contrib[ai[g]] += prev_exit
        M[j] = contrib
        prev_serial, prev_exit = row.serial, row.exit_fh

    pn_i = {p: k for k, p in enumerate(pns)}
    fam_i = {f: k for k, f in enumerate(fams)}
    fe_i = {fe: k for k, fe in enumerate(fes)}
    serial_codes, serial_uniques = pd.factorize(df["serial"])
    event = (df["removal_reason"] == "failure").to_numpy(float)
    return _Design(
        serial_idx=serial_codes, n_serials=len(serial_uniques),
        n_events_serial=np.bincount(serial_codes, event, len(serial_uniques)),
        pn_idx=df["pn"].map(pn_i).to_numpy(),
        fam_idx=df["family"].map(fam_i).to_numpy(),
        fe_idx=np.array([fe_i[(f, e)] for f, e in zip(df["family"], df["env"])]),
        entry=df["entry_fh"].to_numpy(float),
        exit=df["exit_fh"].to_numpy(float),
        event=event,
        M=M, serial=df["serial"].to_numpy(), pns=pns, fams=fams, fes=fes, agencies=agencies,
        fam_of_pn=np.array([fam_i[family_of[p]] for p in pns]),
    )


class _Objective:
    """Negative log posterior and its gradient."""

    def __init__(self, d: _Design):
        self.d = d
        self.P, self.F, self.FE, self.G = len(d.pns), len(d.fams), len(d.fes), len(d.agencies)
        self.sizes = [self.P, self.F, self.F, self.FE, self.G, 1]

    def split(self, x):
        out, k = [], 0
        for s in self.sizes:
            out.append(x[k:k + s])
            k += s
        return out    # log_eta, mu_f, log_beta, gamma, logit_q, log_k

    def x0(self) -> np.ndarray:
        d = self.d
        mean_exit = np.array([d.exit[d.pn_idx == p].mean() for p in range(self.P)])
        log_eta = np.log(np.maximum(mean_exit, 1.0) * 1.2)
        mu = np.array([log_eta[d.fam_of_pn == f].mean() for f in range(self.F)])
        return np.concatenate([log_eta, mu, np.full(self.F, PRIOR_LOG_BETA[0]),
                               np.zeros(self.FE), np.full(self.G, PRIOR_Q[0]), [PRIOR_LOG_K[0]]])

    def __call__(self, x):
        d = self.d
        log_eta_p, mu_f, log_beta_f, gamma, lq, lk = self.split(x)
        k = float(np.exp(lk[0]))
        q = expit(lq)
        beta = np.exp(log_beta_f)[d.fam_idx]
        log_eta = log_eta_p[d.pn_idx] + gamma[d.fe_idx]
        eta = np.exp(log_eta)
        V = d.M @ q
        a1 = V + d.exit
        a0 = V + d.entry
        r1 = a1 / eta
        r0 = a0 / eta
        u1 = r1 ** beta
        with np.errstate(divide="ignore", invalid="ignore"):
            u0 = np.where(a0 > 0, r0 ** beta, 0.0)
            log_r0 = np.where(a0 > 0, np.log(np.where(a0 > 0, r0, 1.0)), 0.0)
        log_r1 = np.log(r1)
        ev = d.event
        # shared gamma frailty per serial, integrated out
        lam = np.bincount(d.serial_idx, u1 - u0, d.n_serials)
        n_i = d.n_events_serial
        ll = np.sum(ev * (np.log(beta) - log_eta + (beta - 1) * log_r1))
        ll += np.sum(gammaln(k + n_i) - gammaln(k) + k * np.log(k) - (k + n_i) * np.log(k + lam))
        wgt = ((k + n_i) / (k + lam))[d.serial_idx]          # d ll / d Lambda_i = -wgt
        g_lk = k * np.sum(digamma(k + n_i) - digamma(k) + np.log(k) + 1.0 - np.log(k + lam) - (k + n_i) / (k + lam))

        # priors
        lp = -0.5 * np.sum(((log_eta_p - mu_f[d.fam_of_pn]) / PRIOR_ETA_SD) ** 2)
        lp += -0.5 * np.sum(((log_beta_f - PRIOR_LOG_BETA[0]) / PRIOR_LOG_BETA[1]) ** 2)
        lp += -0.5 * np.sum((gamma / PRIOR_GAMMA_SD) ** 2)
        lp += -0.5 * np.sum(((lq - PRIOR_Q[0]) / PRIOR_Q[1]) ** 2)
        lp += -0.5 * ((lk[0] - PRIOR_LOG_K[0]) / PRIOR_LOG_K[1]) ** 2
        f = -(ll + lp)

        # gradient of ll
        d_logeta = -ev * beta + wgt * (beta * u1 - beta * u0)            # per spell
        d_beta = ev * (1.0 / beta + log_r1) - wgt * (u1 * log_r1 - u0 * log_r0)
        d_logbeta_spell = d_beta * beta
        with np.errstate(divide="ignore", invalid="ignore"):
            d_a1 = ev * (beta - 1) / a1 - wgt * beta * u1 / a1
            d_a0 = np.where(a0 > 0, wgt * beta * u0 / np.where(a0 > 0, a0, 1.0), 0.0)
        dV = d_a1 + d_a0
        g_log_eta_p = np.bincount(d.pn_idx, d_logeta, self.P)
        g_gamma = np.bincount(d.fe_idx, d_logeta, self.FE)
        g_log_beta = np.bincount(d.fam_idx, d_logbeta_spell, self.F)
        g_lq = (d.M.T @ dV) * q * (1 - q)
        g_mu = np.zeros(self.F)

        # gradient of priors
        resid = (log_eta_p - mu_f[d.fam_of_pn]) / PRIOR_ETA_SD ** 2
        g_log_eta_p -= resid
        g_mu += np.bincount(d.fam_of_pn, resid, self.F)
        g_log_beta -= (log_beta_f - PRIOR_LOG_BETA[0]) / PRIOR_LOG_BETA[1] ** 2
        g_gamma -= gamma / PRIOR_GAMMA_SD ** 2
        g_lq -= (lq - PRIOR_Q[0]) / PRIOR_Q[1] ** 2
        g_lk -= (lk[0] - PRIOR_LOG_K[0]) / PRIOR_LOG_K[1] ** 2
        grad = -np.concatenate([g_log_eta_p, g_mu, g_log_beta, g_gamma, g_lq, [g_lk]])
        return f, grad


@dataclass
class TierCModel:
    """Fitted Tier C model; satisfies the twin's DecisionModel protocol."""
    pns: list[str]
    fams: list[str]
    fes: list[tuple[str, str]]
    agencies: list[str]
    family_of: dict[str, str]
    x: np.ndarray
    cov: np.ndarray
    n_spells: int
    n_failures: int
    n_failures_by_pn: dict[str, int]
    objective_value: float
    rogue_flags: set[int] = field(default_factory=set)
    default_q: float = 0.3

    def __post_init__(self):
        P, F, FE, G = len(self.pns), len(self.fams), len(self.fes), len(self.agencies)
        k = 0
        self.log_eta_p = self.x[k:k + P]; k += P
        self.mu_f = self.x[k:k + F]; k += F
        self.log_beta_f = self.x[k:k + F]; k += F
        self.gamma = self.x[k:k + FE]; k += FE
        self.logit_q = self.x[k:k + G]; k += G
        self.frailty_k = float(np.exp(self.x[k]))
        self._pn = {p: i for i, p in enumerate(self.pns)}
        self._fam = {f: i for i, f in enumerate(self.fams)}
        self._fe = {fe: i for i, fe in enumerate(self.fes)}
        self.q_hat = {a: float(expit(v)) for a, v in zip(self.agencies, self.logit_q)}

    # -- parameters ---------------------------------------------------
    def params(self, pn: str, env: str) -> tuple[float, float]:
        fam = self.family_of[pn]
        beta = float(np.exp(self.log_beta_f[self._fam[fam]])) if fam in self._fam else 1.5
        if pn in self._pn:
            log_eta = self.log_eta_p[self._pn[pn]]
        elif fam in self._fam:
            log_eta = self.mu_f[self._fam[fam]]
        else:
            log_eta = math.log(400.0)
        g = self._fe.get((fam, env))
        if g is not None:
            log_eta += self.gamma[g]
        return beta, float(np.exp(log_eta))

    def cum_hazard(self, pn: str, env: str, a0: float, a1: float) -> float:
        beta, eta = self.params(pn, env)
        return (max(a1, 0.0) / eta) ** beta - (max(a0, 0.0) / eta) ** beta

    def fail_prob(self, pn: str, env: str, age_fh: float, horizon_fh: float) -> float:
        return 1.0 - math.exp(-self.cum_hazard(pn, env, age_fh, age_fh + horizon_fh))

    # -- uncertainty ---------------------------------------------------
    def _offset(self, block: str) -> int:
        P, F, FE = len(self.pns), len(self.fams), len(self.fes)
        return {"log_eta": 0, "mu": P, "log_beta": P + F, "gamma": P + 2 * F, "q": P + 2 * F + FE}[block]

    def q_interval(self, agency: str, level: float = 0.9) -> tuple[float, float, float]:
        i = self._offset("q") + self.agencies.index(agency)
        z = _z(level)
        sd = math.sqrt(max(self.cov[i, i], 0.0))
        m = self.logit_q[self.agencies.index(agency)]
        return float(expit(m)), float(expit(m - z * sd)), float(expit(m + z * sd))

    def env_multiplier(self, family: str, env: str, level: float = 0.9) -> tuple[float, float, float]:
        """eta multiplier for env relative to the family's average environment."""
        idx = [k for k, (f, _e) in enumerate(self.fes) if f == family]
        if (family, env) not in self._fe or len(idx) < 2:
            return 1.0, 1.0, 1.0
        k = self._fe[(family, env)]
        w = np.zeros(len(self.x))
        off = self._offset("gamma")
        for j in idx:
            w[off + j] -= 1.0 / len(idx)
        w[off + k] += 1.0
        m = float(w @ self.x)
        sd = math.sqrt(max(float(w @ self.cov @ w), 0.0))
        z = _z(level)
        return math.exp(m), math.exp(m - z * sd), math.exp(m + z * sd)

    def fail_prob_interval(self, pn: str, env: str, age_fh: float, horizon_fh: float,
                           n_draws: int = 200, seed: int = 0, level: float = 0.8) -> tuple[float, float, float]:
        rng = np.random.default_rng(seed)
        try:
            draws = rng.multivariate_normal(self.x, self.cov, size=n_draws, method="cholesky")
        except np.linalg.LinAlgError:
            draws = rng.multivariate_normal(self.x, self.cov + 1e-6 * np.eye(len(self.x)), size=n_draws)
        vals = []
        for xd in draws:
            m = TierCModel(self.pns, self.fams, self.fes, self.agencies, self.family_of, xd, self.cov,
                           self.n_spells, self.n_failures, self.n_failures_by_pn, self.objective_value)
            vals.append(m.fail_prob(pn, env, age_fh, horizon_fh))
        lo, hi = np.quantile(vals, [(1 - level) / 2, 1 - (1 - level) / 2])
        return self.fail_prob(pn, env, age_fh, horizon_fh), float(lo), float(hi)


def _z(level: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(0.5 + level / 2))


def fit_tier_c(spells: pd.DataFrame, family_of: dict[str, str], hessian: bool = True) -> TierCModel:
    d = build_design(spells, family_of)
    obj = _Objective(d)
    res = minimize(obj, obj.x0(), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    x = res.x
    if hessian:
        cov = _laplace_cov(obj, x)
    else:
        cov = np.eye(len(x)) * 1e-4
    by_pn = {p: int(d.event[d.pn_idx == k].sum()) for k, p in enumerate(d.pns)}
    return TierCModel(d.pns, d.fams, d.fes, d.agencies, family_of, x, cov,
                      n_spells=len(d.exit), n_failures=int(d.event.sum()),
                      n_failures_by_pn=by_pn, objective_value=float(res.fun))


def _laplace_cov(obj: _Objective, x: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    n = len(x)
    Hm = np.zeros((n, n))
    for i in range(n):
        e = np.zeros(n)
        e[i] = eps
        Hm[:, i] = (obj(x + e)[1] - obj(x - e)[1]) / (2 * eps)
    Hm = 0.5 * (Hm + Hm.T)
    try:
        cov = np.linalg.inv(Hm)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(Hm)
    w, U = np.linalg.eigh(0.5 * (cov + cov.T))
    return (U * np.clip(w, 1e-8, None)) @ U.T
