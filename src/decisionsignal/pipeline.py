"""Pipeline steps, each reading and writing data/interim/*.parquet so steps can be re-run alone."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pandas as pd
from tqdm import tqdm

from . import edgar
from .config import PATHS, RESULTS, STUDY_START
from .events import build_events, dedupe_quarterly
from .client import estimate_usd
from .prices import build_prices
from .score import CF_VARIANTS, MAIN_VARIANTS, build_payloads, counterfactual_sample, score_events
from .text import looks_like_earnings_release, narrative_text
from .universe import build_universe, coverage_report


def step_universe(end: date) -> pd.DataFrame:
    uni = build_universe(end)
    cov = coverage_report(uni)
    (RESULTS / "coverage_universe.json").write_text(json.dumps(cov, indent=2))
    print(f"universe: {cov['companies']} S&P 100 companies, {cov['spells']} spells, {cov['mapped_to_cik']} mapped to CIK, "
          f"{len(cov['unmapped_tickers'])} unmapped tickers (see results/coverage_universe.json)")
    return uni


def step_filings(start: date, end: date, limit_ciks: int | None = None) -> pd.DataFrame:
    uni = pd.read_parquet(PATHS.universe)
    df = edgar.collect_filings(uni, start, end, limit_ciks=limit_ciks)
    print(f"filings: {len(df)} 8-K Item 2.02 filings during S&P 500 membership; "
          f"{df['exhibit_url'].notna().sum() if len(df) else 0} with an EX-99 exhibit")
    return df


def step_texts() -> pd.DataFrame:
    filings = pd.read_parquet(PATHS.filings)
    filings = filings[filings["exhibit_url"].notna()]
    rows = []
    for f in tqdm(filings.to_dict("records"), desc="exhibits"):
        try:
            html = edgar.fetch_exhibit_html(f["exhibit_url"])
        except httpx.HTTPStatusError as exc:
            print(f"skip {f['accessionNumber']}: {exc.response.status_code}")
            continue
        text = narrative_text(html)
        rows.append({"accessionNumber": f["accessionNumber"], "text": text, "chars": len(text),
                     "earnings_heuristic": looks_like_earnings_release(text)})
    df = pd.DataFrame(rows)
    df.to_parquet(PATHS.texts, index=False)
    print(f"texts: {len(df)} exhibits, median {df['chars'].median():.0f} chars, "
          f"{df['earnings_heuristic'].mean():.0%} look like earnings releases")
    return df


def step_prices(end: date) -> pd.DataFrame:
    filings = pd.read_parquet(PATHS.filings)
    tickers = filings["price_ticker"].dropna().unique().tolist()
    df = build_prices(tickers, STUDY_START, end)
    missing = sorted(set(t.replace(".", "-") for t in tickers) - set(df["ticker"].unique()))
    (RESULTS / "coverage_prices.json").write_text(json.dumps({"requested": len(tickers), "missing": missing}, indent=2))
    print(f"prices: {df['ticker'].nunique()} symbols, {len(df)} rows; {len(missing)} tickers without data")
    return df


def step_events() -> pd.DataFrame:
    filings = pd.read_parquet(PATHS.filings)
    texts = pd.read_parquet(PATHS.texts)[["accessionNumber"]]
    filings = filings.merge(texts, on="accessionNumber")
    prices = pd.read_parquet(PATHS.prices)
    ev = build_events(filings, prices)
    ev = dedupe_quarterly(ev)
    ev.to_parquet(PATHS.events, index=False)
    print("events:", ev["drop_reason"].fillna("ok").value_counts().to_dict(),
          "| by split:", ev[ev["drop_reason"].isna()]["split"].value_counts().to_dict())
    return ev


def _scorable(split: str, limit: int | None) -> pd.DataFrame:
    ev = pd.read_parquet(PATHS.events)
    ev = ev[ev["drop_reason"].isna()].merge(pd.read_parquet(PATHS.texts), on="accessionNumber")
    if split != "all":
        ev = ev[ev["split"] == split]
    ev = ev.sort_values("accepted_et")
    return ev.head(limit) if limit else ev


def step_estimate(split: str, limit: int | None, n_cf: int) -> dict:
    ev = _scorable(split, limit)
    main = build_payloads(ev, MAIN_VARIANTS)
    cf = build_payloads(counterfactual_sample(ev, n_cf), CF_VARIANTS) if n_cf else []
    est = {"events": int(len(ev)), "requests": len(main) + len(cf),
           "usd_main": round(estimate_usd([p for *_, p in main]), 4),
           "usd_counterfactual": round(estimate_usd([p for *_, p in cf]), 4)}
    est["usd_total"] = round(est["usd_main"] + est["usd_counterfactual"], 4)
    print(json.dumps(est, indent=2))
    return est


def step_score(split: str, limit: int | None, n_cf: int) -> pd.DataFrame:
    ev = _scorable(split, limit)
    new = [score_events(ev, MAIN_VARIANTS)]
    if n_cf:
        new.append(score_events(counterfactual_sample(ev, n_cf), CF_VARIANTS))
    ans = pd.concat(new, ignore_index=True)
    if PATHS.answers.exists():
        old = pd.read_parquet(PATHS.answers)
        ans = pd.concat([old, ans]).drop_duplicates(["accessionNumber", "variant", "question"], keep="last")
    ans.to_parquet(PATHS.answers, index=False)
    errors = ans["error"].notna().sum()
    print(f"answers: {len(ans)} rows, {errors} errors")
    return ans
