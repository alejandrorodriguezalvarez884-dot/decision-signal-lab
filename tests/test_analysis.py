"""The statistics must find a planted signal and must not find one in noise."""

import numpy as np
import pandas as pd

from decisionsignal import analysis as A


def _panel(beta: float, n_weeks=120, per_week=25, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2021-01-04", periods=n_weeks, freq="W-MON")
    rows = []
    for w in weeks:
        common = rng.normal(0, 0.02)  # same-week shock shared by all events
        for _ in range(per_week):
            s = rng.normal()
            rows.append({"entry_session": w, "sig": s, "y": common + beta * 0.01 * s + rng.normal(0, 0.06)})
    return pd.DataFrame(rows)


def test_detects_planted_signal():
    d = _panel(beta=1.0)
    r = A.fama_macbeth_ic(d, "sig", "y", horizon=5)
    assert r["mean_ic"] > 0.1 and r["p"] < 0.001
    q = A.quintile_spread(d, "sig", "y", A.design_edges(d["sig"]))
    assert q["spread"] > 0 and q["ci_low"] > 0
    assert A.permutation_placebo(d, "sig", "y")["p_perm"] < 0.01


def test_noise_is_not_significant_most_of_the_time():
    pvals = [A.fama_macbeth_ic(_panel(beta=0.0, seed=s), "sig", "y", 5)["p"] for s in range(20)]
    assert np.mean(np.array(pvals) < 0.05) <= 0.15  # ~5% false positives expected


def test_incremental_regression_controls_absorb_redundant_signal():
    d = _panel(beta=1.0)
    d["copy"] = d["sig"] + np.random.default_rng(1).normal(0, 0.01, len(d))
    r = A.incremental_regression(d, "copy", "y", controls=["sig"])
    assert r["p"] > 0.01  # nothing left once the true driver is controlled for


def test_holm():
    adj = A.holm({"a": 0.01, "b": 0.04, "c": 0.5})
    assert adj["a"] == 0.03 and adj["b"] == 0.08 and adj["c"] == 0.5
