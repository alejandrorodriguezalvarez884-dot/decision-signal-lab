"""The public dataset behind the earnings radar: what each results release says, as probabilities.

Text only. Nothing in this module reads prices, returns or the day-0 reaction, and nothing it
publishes is a forecast. Each release gets two requests: the text questions the study already
asked (``questions.TEXT_QUESTIONS`` on the identity-masked text, so every release scored during
the study is served from the cache) and the theme questions.

``radar/releases.json`` is the record: one entry per published release, plus the filings that
were looked at and left out. ``radar/summary.json`` is derived from it and can be rebuilt at any
time with ``write_summary``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from . import edgar
from . import questions as Q
from .anonymize import anonymize
from .client import DecisionClient, estimate_usd, payload, request_key
from .config import (
    DECIDER_MODEL,
    DECIDER_PRICE_PER_INPUT_TOKEN,
    PATHS,
    RADAR_DEDUPE_DAYS,
    RADAR_LATEST,
    RADAR_LOOKBACK_DAYS,
    RADAR_MIN_EARNINGS_PROB,
    RADAR_THEME_THRESHOLD,
    ROOT,
)
from .radar_universe import COMPANIES, TICKER_BY_CIK
from .score import flatten_answer
from .text import narrative_text

GUIDANCE_CLASSES = tuple(Q.TEXT_QUESTIONS["guidance"]["criteria"])
# Published per release, each on a 0..1 scale. `naive_reaction` is asked (it is part of the
# cached request) but not published: it is a guess about prices, which the radar does not make.
SCORE_FIELDS = ("results_strength", "outlook_tone", "uncertainty", "demand_weakness", "margin_pressure")
FLAG_FIELDS = ("demand_weakness", "margin_pressure", "uncertainty")
THEMES = tuple(Q.THEME_QUESTIONS)

VALIDATION_RESULT = ROOT / "validation" / "guidance_result.json"


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


# =========================================================================== scoring
def requests_for(row: dict) -> tuple[dict, dict]:
    """(core, themes) payloads for one filing. Same masking as the study, so the cache hits."""
    anon = anonymize(row["text"], row.get("sec_name") or "", [TICKER_BY_CIK[int(row["cik"])]])
    return payload(*Q.text_request(anon)), payload(*Q.theme_request(anon))


def _answers(resp: dict) -> dict[str, dict] | None:
    rows = flatten_answer("", "", resp)
    if any(r.get("error") for r in rows):
        return None
    return {r["question"]: r for r in rows}


def release_record(row: dict, core: dict, themes: dict | None) -> dict | None:
    """One scored filing, or None when the model did not answer (the filing is retried later).
    ``themes`` is None when the theme questions were not asked."""
    a, t = _answers(core), _answers(themes) if themes is not None else {}
    if a is None or t is None:
        return None
    acc, cik = row["accessionNumber"], int(row["cik"])
    accepted = pd.Timestamp(row["accepted_et"])
    g = a["guidance"]
    return {
        "id": acc,
        "ticker": TICKER_BY_CIK[cik],
        "accepted": accepted.isoformat(),
        "date": accepted.date().isoformat(),
        "quarter": f"{accepted.year}Q{accepted.quarter}",
        "url": edgar.ARCHIVE.format(cik=cik, acc_nodash=acc.replace("-", "")) + f"{acc}-index.htm",
        "exhibit": row.get("exhibit_url"),
        "is_earnings": _r(a["is_earnings_release"]["value"]),
        "guidance": g["choice"],
        "guidance_p": {k: _r(g[f"p_{k}"]) for k in GUIDANCE_CLASSES},
        **{f: _r(a[f]["value"]) for f in SCORE_FIELDS},
        "themes": {k: _r(t[k]["value"]) for k in THEMES} if t else {},
        "tokens": sum(int(r.get("usage", {}).get("input_tokens", 0)) for r in (core, themes) if r),
    }


def _payloads(filings: pd.DataFrame, themes: bool) -> list[dict]:
    """Per filing, the core request and (with ``themes``) the theme request, in that order."""
    return [p for row in filings.to_dict("records") for p in requests_for(row)[: 2 if themes else 1]]


def estimate(filings: pd.DataFrame, themes: bool = True, client: DecisionClient | None = None) -> dict:
    client = client or DecisionClient()
    flat = _payloads(filings, themes)
    todo = [p for p in flat if client.cache.get(request_key(p)) is None]
    return {"filings": int(len(filings)), "requests": len(flat), "not_cached": len(todo),
            "usd": round(estimate_usd(todo), 4), "spent_so_far_usd": round(client.spend.prior_usd, 4)}


def score(filings: pd.DataFrame, themes: bool = True,
          client: DecisionClient | None = None) -> tuple[list[dict], dict[str, str]]:
    """Score filings. Returns the records and, for filings the API refuses, the reason."""
    client = client or DecisionClient()
    rows = filings.to_dict("records")
    resps = client.call_many(_payloads(filings, themes), desc="Radar") if rows else []
    step = 2 if themes else 1
    records, refused = [], {}
    for i, row in enumerate(rows):
        core, themes_resp = resps[step * i], resps[step * i + 1] if themes else None
        if "unprocessable" in (core.get("error"), (themes_resp or {}).get("error")):
            refused[row["accessionNumber"]] = "unprocessable"
            continue
        rec = release_record(row, core, themes_resp)
        if rec is not None:
            records.append(rec)
    return records, refused


def select(records: list[dict], published: list[dict] = ()) -> tuple[list[dict], dict[str, str]]:
    """Split scored filings into releases to publish and filings to leave out.

    A filing is published when the model reads it as a results release and the company has no
    published release in the previous ``RADAR_DEDUPE_DAYS`` days (companies often file a second
    Item 2.02 with slides or a correction). ``published`` are releases already out; they are
    never dropped, only used as the reference for duplicates.
    """
    keep, skipped = [], {}
    last: dict[str, pd.Timestamp] = {}
    for r in published:
        t = pd.Timestamp(r["accepted"])
        last[r["ticker"]] = max(last.get(r["ticker"], t), t)
    for r in sorted(records, key=lambda r: (pd.Timestamp(r["accepted"]), r["id"])):
        t = pd.Timestamp(r["accepted"])
        prev = last.get(r["ticker"])
        if r["is_earnings"] < RADAR_MIN_EARNINGS_PROB:
            skipped[r["id"]] = "not_earnings"
        elif prev is not None and abs((t - prev).days) < RADAR_DEDUPE_DAYS:
            skipped[r["id"]] = "duplicate"
        else:
            keep.append(r)
            last[r["ticker"]] = t
    return keep, skipped


# =========================================================================== storage
def load() -> dict:
    if PATHS.radar_releases.exists():
        return json.loads(PATHS.radar_releases.read_text())
    return {"model": DECIDER_MODEL, "skipped": {}, "releases": []}


def save(data: dict) -> None:
    """One release per line, oldest first, so a daily update is a few added lines in git."""
    releases = sorted(data["releases"], key=lambda r: (r["accepted"], r["id"]))
    lines = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in releases)
    head = json.dumps({"model": data["model"], "skipped": dict(sorted(data["skipped"].items()))},
                      ensure_ascii=False, separators=(",", ":"))
    PATHS.radar_releases.parent.mkdir(parents=True, exist_ok=True)
    PATHS.radar_releases.write_text(f'{head[:-1]},"releases":[\n{lines}\n]}}\n')


# =========================================================================== full history
def local_filings() -> pd.DataFrame:
    """Every downloaded Item 2.02 filing of a covered company that has text."""
    f = pd.read_parquet(PATHS.filings).merge(
        pd.read_parquet(PATHS.texts)[["accessionNumber", "text"]], on="accessionNumber")
    return f[f["cik"].isin(TICKER_BY_CIK) & (f["text"].str.len() > 0)].sort_values("accepted_et")


def build(themes: bool = True, client: DecisionClient | None = None) -> dict:
    """Rebuild the dataset from the local download. Releases added by ``update`` that the local
    download does not have are kept as they are."""
    filings = local_filings()
    records, refused = score(filings, themes, client)
    local_ids = set(filings["accessionNumber"])
    data = load()
    extra = [r for r in data["releases"] if r["id"] not in local_ids]
    keep, skipped = select(records)
    data["releases"] = keep + [r for r in extra if r["id"] not in {k["id"] for k in keep}]
    data["skipped"] = {k: v for k, v in data["skipped"].items() if k not in local_ids} | skipped | refused
    save(data)
    return data


# =========================================================================== daily update
def fetch_new_filings(known: set[str], since: date, until: date) -> tuple[pd.DataFrame, dict[str, str]]:
    """Item 2.02 filings of covered companies in the window that are not in ``known``, with text."""
    rows, skipped = [], {}
    for ticker, c in COMPANIES.items():
        try:
            found = edgar.list_item_202_filings(c.cik, since, until, fresh=True)
        except httpx.HTTPStatusError as exc:
            print(f"skip {ticker}: {exc.response.status_code}")
            continue
        for rec in found.to_dict("records"):
            acc = rec["accessionNumber"]
            if acc in known:
                continue
            try:
                docs = edgar.fetch_filing_docs(c.cik, acc)
            except (httpx.HTTPStatusError, ValueError) as exc:
                print(f"skip {acc}: {exc}")  # not recorded: the index page may not be up yet
                continue
            if not docs.exhibit_url:
                skipped[acc] = "no_exhibit"
                continue
            text = narrative_text(edgar.fetch_exhibit_html(docs.exhibit_url))
            if not text:
                skipped[acc] = "no_text"
                continue
            rows.append({"accessionNumber": acc, "cik": c.cik, "sec_name": rec.get("sec_name"),
                         "accepted_et": docs.accepted_et, "exhibit_url": docs.exhibit_url, "text": text})
    return pd.DataFrame(rows), skipped


def pending(data: dict, today: date | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Filings on EDGAR that the dataset has not seen yet. Downloads, but does not call the model."""
    today = today or date.today()
    known = {r["id"] for r in data["releases"]} | set(data["skipped"])
    return fetch_new_filings(known, today - timedelta(days=RADAR_LOOKBACK_DAYS), today)


def check(today: date | None = None, themes: bool = True, client: DecisionClient | None = None) -> dict:
    """What `update` would do and cost, without spending anything or writing anything."""
    filings, skipped = pending(load(), today)
    new = [{"ticker": TICKER_BY_CIK[int(r["cik"])], "date": pd.Timestamp(r["accepted_et"]).date().isoformat(),
            "id": r["accessionNumber"]} for r in filings.to_dict("records")]
    cost = estimate(filings, themes, client) if len(filings) else {"requests": 0, "not_cached": 0, "usd": 0.0}
    return {"new_filings": new, "without_text_or_exhibit": len(skipped),
            "requests": cost["requests"], "estimated_usd": cost["usd"]}


def update(today: date | None = None, themes: bool = True, client: DecisionClient | None = None) -> list[dict]:
    """Look for filings since the last update, score them and add them. Returns the new releases."""
    data = load()
    filings, skipped = pending(data, today)
    records, refused = score(filings, themes, client) if len(filings) else ([], {})
    keep, left_out = select(records, published=data["releases"])
    data["releases"] += keep
    data["skipped"] |= skipped | refused | left_out
    save(data)
    print(f"radar: {len(filings)} new filings, {len(keep)} published, "
          f"{len(skipped) + len(refused) + len(left_out)} left out")
    return keep


# =========================================================================== summary
def _frame(releases: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(releases)
    df["when"] = pd.to_datetime(df["date"])
    for k in THEMES:
        df[f"theme_{k}"] = df["themes"].map(lambda t, k=k: t.get(k))
    df["name"] = df["ticker"].map(lambda t: COMPANIES[t].name)
    df["sector"] = df["ticker"].map(lambda t: COMPANIES[t].sector)
    df = df.sort_values(["accepted", "id"]).reset_index(drop=True)
    df["prev_guidance"] = df.groupby("ticker")["guidance"].shift(1)
    return df


def _guidance_shares(g: pd.DataFrame) -> dict[str, float]:
    return {c: _r((g["guidance"] == c).mean(), 4) for c in GUIDANCE_CLASSES}


def _block(g: pd.DataFrame) -> dict:
    shares = _guidance_shares(g)
    return {
        "n": int(len(g)),
        "guidance": shares,
        "guidance_net": _r(shares["raised"] - shares["lowered"], 4),
        "scores": {f: _r(g[f].mean(), 4) for f in SCORE_FIELDS},
        # Share of releases at or above the midpoint of the scale: "describes weakening demand",
        # "describes pressured margins", "at least a moderate amount of caution".
        "flags": {f: _r((g[f] >= 0.5).mean(), 4) for f in FLAG_FIELDS},
        # Share of the releases that were asked each theme question; None when none were.
        "themes": {k: _r((g[f"theme_{k}"].dropna() >= RADAR_THEME_THRESHOLD).mean(), 4)
                   if g[f"theme_{k}"].notna().any() else None for k in THEMES},
    }


def _none(x):
    return None if pd.isna(x) else x


def summarize(releases: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    df = _frame(releases)
    current = f"{today.year}Q{(today.month - 1) // 3 + 1}"

    # Quarters are quarters of publication: a release out in February counts in Q1, whatever
    # fiscal period it reports.
    quarters = [{"quarter": q, "partial": q == current, **_block(g)} for q, g in df.groupby("quarter")]

    end = pd.Timestamp(today)
    year, prior = df[df["when"] > end - pd.Timedelta(days=365)], df[
        (df["when"] <= end - pd.Timedelta(days=365)) & (df["when"] > end - pd.Timedelta(days=730))]
    sectors = []
    for sector, g in year.groupby("sector"):
        p = prior[prior["sector"] == sector]
        sectors.append({"sector": sector, "companies": int(g["ticker"].nunique()), **_block(g),
                        "prior": _block(p) if len(p) else None})
    sectors.sort(key=lambda s: -s["guidance_net"])

    companies = []
    for ticker, g in df.groupby("ticker"):
        last = g.iloc[-1]
        companies.append({"ticker": ticker, "name": COMPANIES[ticker].name, "sector": COMPANIES[ticker].sector,
                          "n": int(len(g)), "last_date": last["date"], "last_guidance": last["guidance"],
                          "prev_guidance": _none(last["prev_guidance"])})
    companies.sort(key=lambda c: c["name"].lower())

    latest = [{"id": r["id"], "ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "date": r["date"],
               "guidance": r["guidance"], "prev_guidance": _none(r["prev_guidance"]),
               "guidance_confidence": r["guidance_p"][r["guidance"]],
               **{f: r[f] for f in SCORE_FIELDS},
               "themes": [k for k in THEMES if r["themes"].get(k, 0) >= RADAR_THEME_THRESHOLD], "url": r["url"]}
              for r in df.tail(RADAR_LATEST).iloc[::-1].to_dict("records")]

    tokens = int(df["tokens"].sum())
    return {
        "meta": {
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": DECIDER_MODEL,
            "releases": int(len(df)),
            "companies": int(df["ticker"].nunique()),
            "first_date": df["date"].min(),
            "last_date": df["date"].max(),
            "current_quarter": current,
            "input_tokens": tokens,
            "api_cost_usd": round(tokens * DECIDER_PRICE_PER_INPUT_TOKEN, 2),
            "theme_threshold": RADAR_THEME_THRESHOLD,
            "guidance_classes": {k: v for k, v in Q.TEXT_QUESTIONS["guidance"]["criteria"].items()},
            "questions": {k: Q.TEXT_QUESTIONS[k]["instructions"] for k in ("guidance", *SCORE_FIELDS)},
            "theme_questions": {k: v["instructions"] for k, v in Q.THEME_QUESTIONS.items()},
            "has_themes": bool(df[[f"theme_{k}" for k in THEMES]].notna().any().any()),
            "validation": json.loads(VALIDATION_RESULT.read_text()) if VALIDATION_RESULT.exists() else None,
        },
        "quarters": quarters,
        "sectors": sectors,
        "companies": companies,
        "latest": latest,
    }


def write_summary(today: date | None = None) -> dict:
    summary = summarize(load()["releases"], today)
    PATHS.radar_summary.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    return summary
