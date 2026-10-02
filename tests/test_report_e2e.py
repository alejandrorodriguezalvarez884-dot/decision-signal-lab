"""End-to-end run of features -> baselines -> statistics -> report on synthetic data, no network."""

import dataclasses
import json

import numpy as np
import pandas as pd

from jevsignal import questions as Q
from jevsignal import report
from jevsignal.config import PATHS
from jevsignal.score import CF_VARIANTS, MAIN_VARIANTS, flatten_answer

TEXT = "The Company reported third quarter results. Revenue grew strongly and we raised our outlook."


def _fake_response(qs: dict, rng) -> dict:
    ans = {}
    for qid, q in qs.items():
        if q["type"] == "noul":
            ans[qid] = {"type": "noul", "noul": float(rng.uniform())}
        else:
            opts = list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
            p = rng.dirichlet(np.ones(len(opts)))
            a = {"type": q["type"], "probabilities": dict(zip(opts, p)), "confidence": float(p.max())}
            if q["type"] == "choice":
                a["choice"] = opts[int(p.argmax())]
            else:
                a["score"] = float(sum(i * pi for i, pi in enumerate(p)))
            ans[qid] = a
    return {"model": "jev-1.13.0", "answers": ans, "usage": {"input_tokens": 100}}


def test_report_runs_end_to_end(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    n = 900
    # Earnings seasons: events bunch into a few weeks, like real data.
    weeks = (list(pd.date_range("2021-02-01", "2024-11-30", freq="W-MON")[::6])
             + list(pd.date_range("2025-01-06", "2025-06-30", freq="W-MON")[::2]))
    entry = pd.Series(rng.choice(weeks, n) + pd.to_timedelta(rng.integers(0, 4, n), "D")).sort_values().reset_index(drop=True)
    ev = pd.DataFrame({
        "accessionNumber": [f"acc{i}" for i in range(n)],
        "cik": rng.integers(1, 200, n), "sec_name": "ACME CORP", "sic": 3572, "price_ticker": "ACME",
        "accepted_et": (entry - pd.Timedelta(days=1)).dt.tz_localize("America/New_York"),
        "entry_session": entry, "r0_abn": rng.normal(0, 0.05, n), "momentum": rng.normal(0, 0.1, n),
        "log_dollar_vol": rng.normal(18, 1, n), "drop_reason": None,
    })
    ev["r0_z"] = ev["r0_abn"] / 0.02
    ev["event_date"] = (entry - pd.Timedelta(days=1)).dt.normalize()
    ev["split"] = np.where(ev["event_date"] >= "2025-01-01", "holdout", "design")
    for h in (1, 5, 20, 60):
        ev[f"fwd_abn_{h}"] = rng.normal(0, 0.08, n)
        ev[f"fwd_sec_abn_{h}"] = rng.normal(0, 0.07, n)

    rows = []
    sets = {"text_raw": Q.TEXT_QUESTIONS, "text_anon": Q.TEXT_QUESTIONS, "react_raw": Q.REACTION_QUESTIONS,
            "react_anon": Q.REACTION_QUESTIONS, "probe": Q.PROBE_QUESTIONS}
    for acc in ev["accessionNumber"]:
        for v in MAIN_VARIANTS:
            rows += flatten_answer(acc, v, _fake_response(sets[v], rng))
    for acc in ev["accessionNumber"][:50]:
        for v in CF_VARIANTS:
            rows += flatten_answer(acc, v, _fake_response(Q.REACTION_QUESTIONS, rng))
    answers = pd.DataFrame(rows)
    # make most releases count as earnings releases
    m = answers["question"] == "is_earnings_release"
    answers.loc[m, "value"] = 0.9

    paths = dataclasses.replace(
        PATHS, events=tmp_path / "e.parquet", texts=tmp_path / "t.parquet",
        answers=tmp_path / "a.parquet", features=tmp_path / "f.parquet",
    )
    ev.to_parquet(paths.events)
    pd.DataFrame({"accessionNumber": ev["accessionNumber"],
                  "text": [TEXT + (" Losses and impairment." if i % 3 else " Record growth.") for i in range(n)]}).to_parquet(paths.texts)
    answers.to_parquet(paths.answers)
    monkeypatch.setattr(report, "PATHS", paths)
    monkeypatch.setattr(report, "RESULTS", tmp_path)
    monkeypatch.setattr(report.A, "N_BOOT", 50)
    monkeypatch.setattr(report.A, "N_PERM", 50)

    res = report.run(include_holdout=True)
    assert set(res["splits"]) == {"design", "holdout"}
    primary = res["splits"]["holdout"]["signals_primary_horizon"][0]
    assert primary["signal"] == "react_anon__nvr"
    assert primary["p"] > 0.001  # pure noise must not look like a discovery
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Results")
    json.loads((tmp_path / "results.json").read_text())
    assert (tmp_path / "quintiles_holdout.png").exists()
