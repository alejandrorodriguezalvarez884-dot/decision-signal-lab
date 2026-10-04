"""Statistics. Events cluster on the same days (earnings season), so every test treats the
entry *week* as the unit of independence: Fama-MacBeth weekly rank ICs with Newey-West errors,
week-block bootstrap, within-week permutation placebos, and week-clustered regressions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

MIN_EVENTS_PER_WEEK = 5
N_BOOT = 2000
N_PERM = 1000


def _week(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["entry_session"]).dt.to_period("W-FRI")


def winsorize(s: pd.Series, ref: pd.Series | None = None, q: float = 0.01) -> pd.Series:
    ref = s if ref is None else ref
    lo, hi = ref.quantile(q), ref.quantile(1 - q)
    return s.clip(lo, hi)


def _nw_lags(horizon: int) -> int:
    # Overlapping holding periods: a 20-session horizon overlaps ~4 subsequent weeks.
    return max(1, math.ceil(horizon / 5))


def weekly_ic(df: pd.DataFrame, signal: str, target: str) -> pd.Series:
    d = df[[signal, target]].assign(week=_week(df)).dropna()
    out = {}
    for wk, g in d.groupby("week"):
        if len(g) >= MIN_EVENTS_PER_WEEK and g[signal].nunique() > 1:
            out[wk] = stats.spearmanr(g[signal], g[target]).statistic
    return pd.Series(out, dtype=float).sort_index()


def newey_west_mean(x: pd.Series, lags: int) -> tuple[float, float, float]:
    x = x.dropna()
    if len(x) < 8:
        return float(x.mean()) if len(x) else np.nan, np.nan, np.nan
    res = sm.OLS(x.values, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags}, use_t=True)
    return float(res.params[0]), float(res.tvalues[0]), float(res.pvalues[0])


def fama_macbeth_ic(df: pd.DataFrame, signal: str, target: str, horizon: int) -> dict:
    ics = weekly_ic(df, signal, target)
    mean, t, p = newey_west_mean(ics, _nw_lags(horizon))
    return {"signal": signal, "target": target, "weeks": int(len(ics)), "mean_ic": mean, "t_nw": t, "p": p,
            "share_positive_weeks": float((ics > 0).mean()) if len(ics) else np.nan}


def pooled_ic_bootstrap(df: pd.DataFrame, signal: str, target: str, seed: int = 0) -> dict:
    d = df[[signal, target]].assign(week=_week(df)).dropna()
    if len(d) < 20:
        return {"pooled_ic": np.nan, "ci_low": np.nan, "ci_high": np.nan, "n": int(len(d))}
    point = stats.spearmanr(d[signal], d[target]).statistic
    groups = {w: g for w, g in d.groupby("week")}
    weeks = list(groups)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(N_BOOT):
        sample = pd.concat([groups[weeks[i]] for i in rng.integers(0, len(weeks), len(weeks))])
        boots.append(stats.spearmanr(sample[signal], sample[target]).statistic)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return {"pooled_ic": float(point), "ci_low": float(lo), "ci_high": float(hi), "n": int(len(d))}


def permutation_placebo(df: pd.DataFrame, signal: str, target: str, seed: int = 0) -> dict:
    """Shuffle the signal *within* each week; compare the real mean weekly IC to that null."""
    d = df[[signal, target, "entry_session"]].dropna().copy()
    real = weekly_ic(d, signal, target).mean()
    # Spearman = Pearson on ranks; pre-rank each week once, then permute the ranks.
    weeks = []
    for _, g in d.groupby(_week(d)):
        if len(g) >= MIN_EVENTS_PER_WEEK and g[signal].nunique() > 1:
            x = stats.rankdata(g[signal]); y = stats.rankdata(g[target])
            weeks.append(((x - x.mean()) / x.std(), (y - y.mean()) / y.std()))
    rng = np.random.default_rng(seed)
    null = np.array([
        np.mean([np.mean(rng.permutation(x) * y) for x, y in weeks]) for _ in range(N_PERM)
    ]) if weeks else np.array([np.nan])
    p = (np.sum(np.abs(null) >= abs(real)) + 1) / (len(null) + 1)
    return {"real_mean_ic": float(real), "null_sd": float(np.nanstd(null)), "p_perm": float(p)}


def design_edges(design_values: pd.Series) -> np.ndarray:
    """Quintile breakpoints. Always computed on the design split, then applied to any split."""
    return design_values.dropna().quantile([0.2, 0.4, 0.6, 0.8]).values


def quintile_spread(df: pd.DataFrame, signal: str, target: str, edges: np.ndarray, seed: int = 0) -> dict:
    """Paper long-short: mean target in top minus bottom quintile (no orders, no costs)."""
    d = df[[signal, target, "entry_session"]].dropna().copy()
    if len(np.unique(edges)) < 4 or len(d) < 20:
        return {"q_means": None, "spread": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    d["q"] = np.searchsorted(edges, d[signal].values, side="right") + 1
    means = d.groupby("q")[target].mean()
    spread = means.get(5, np.nan) - means.get(1, np.nan)
    d["week"] = _week(d)
    groups = {w: g for w, g in d.groupby("week")}
    weeks = list(groups)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(N_BOOT):
        s = pd.concat([groups[weeks[i]] for i in rng.integers(0, len(weeks), len(weeks))])
        m = s.groupby("q")[target].mean()
        boots.append(m.get(5, np.nan) - m.get(1, np.nan))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return {"q_means": {int(k): float(v) for k, v in means.items()}, "q_counts": d["q"].value_counts().sort_index().to_dict(),
            "spread": float(spread), "ci_low": float(lo), "ci_high": float(hi)}


def incremental_regression(df: pd.DataFrame, signal: str, target: str, controls: list[str]) -> dict:
    """OLS of the (winsorized) target on the standardized signal plus controls, SE clustered by week."""
    cols = [signal, target, *controls]
    d = df[cols + ["entry_session"]].dropna().copy()
    if len(d) < 30:
        return {"n": int(len(d)), "coef": np.nan, "t": np.nan, "p": np.nan}
    d[target] = winsorize(d[target])
    X = d[[signal, *controls]].astype(float)
    X = (X - X.mean()) / X.std().replace(0, 1)
    X = sm.add_constant(X)
    groups = pd.factorize(_week(d))[0]
    res = sm.OLS(d[target].astype(float), X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return {"n": int(len(d)), "coef_per_sd": float(res.params[signal]), "t": float(res.tvalues[signal]),
            "p": float(res.pvalues[signal]), "r2": float(res.rsquared), "controls": controls}


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(((k, v) for k, v in pvals.items() if pd.notna(v)), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def sensitivity_to_reaction(features: pd.DataFrame) -> dict:
    """Does the model's verdict move when only the reaction changes? It should fall as the move rises."""
    cols = ["cf_strong_neg__fvr", "cf_flat__fvr", "cf_strong_pos__fvr"]
    if not all(c in features for c in cols):
        return {}
    d = features[cols].dropna()
    monotone = ((d[cols[0]] >= d[cols[1]]) & (d[cols[1]] >= d[cols[2]])).mean()
    unchanged = ((d[cols].max(axis=1) - d[cols].min(axis=1)) < 0.05).mean()
    return {"n": int(len(d)), "mean_signal": d.mean().to_dict(), "share_monotone": float(monotone),
            "share_insensitive": float(unchanged)}
