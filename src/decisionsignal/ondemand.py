"""Analyse the latest results release of any SEC registrant when someone asks for it.

The same method as the radar dataset, run for one company: find its newest Item 2.02 filings on
EDGAR, read the press release, ask the model the same questions. Every filing is read once and
kept in a store, so asking again costs nothing. Text only, like the rest of the radar.

The published dataset (``radar/``) is not consulted: it feeds the market trends, and a company
of the study is read here like any other.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Generator, Iterator, Protocol

import httpx
import pandas as pd

from . import edgar
from . import questions as Q
from . import radar as R
from .client import BudgetExceeded, DecisionClient
from .config import (
    DATA,
    DECIDER_MODEL,
    ONDEMAND_LOOKBACK_DAYS,
    ONDEMAND_MAX_FILINGS,
    ONDEMAND_REQUEST_MAX_USD,
    RADAR_DEDUPE_DAYS,
    RADAR_MIN_EARNINGS_PROB,
    ondemand_daily_max_usd,
    ondemand_total_max_usd,
    sec_user_agent,
)
from .radar_universe import COMPANIES
from .text import narrative_text
from .universe import SEC_TICKERS_URL

TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
# Questions the model answers about each release: the text questions and the themes.
N_QUESTIONS = len(Q.TEXT_QUESTIONS) + len(Q.THEME_QUESTIONS)


class UnknownCompany(LookupError):
    pass


class NoResultsRelease(LookupError):
    """The company has no readable results release in the lookback window."""


class DailyBudgetReached(RuntimeError):
    """The service has spent what it may today, or what it may in total."""


# =========================================================================== companies
@dataclass(frozen=True)
class CompanyRef:
    ticker: str
    cik: int
    name: str


def _fetch_sec_tickers() -> list[dict]:
    resp = httpx.get(SEC_TICKERS_URL, headers={"User-Agent": sec_user_agent()}, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return list(resp.json().values())


class Directory:
    """SEC's list of tickers, kept in memory and refreshed once a day."""

    def __init__(self, fetch: Callable[[], list[dict]] = _fetch_sec_tickers, ttl_seconds: int = 86_400):
        self._fetch, self._ttl = fetch, ttl_seconds
        self._lock = threading.Lock()
        self._loaded = 0.0
        self._by_ticker: dict[str, CompanyRef] = {}
        self._rows: list[CompanyRef] = []

    def _load(self) -> None:
        with self._lock:
            if self._rows and time.monotonic() - self._loaded < self._ttl:
                return
            rows = [CompanyRef(str(r["ticker"]).upper(), int(r["cik_str"]), str(r["title"])) for r in self._fetch()]
            self._rows = rows  # SEC lists them roughly by size, largest first
            self._by_ticker = {r.ticker: r for r in rows}
            self._loaded = time.monotonic()

    def get(self, ticker: str) -> CompanyRef:
        if not TICKER_RE.match(ticker or ""):
            raise UnknownCompany(ticker)
        self._load()
        key = ticker.upper().replace(".", "-")
        ref = self._by_ticker.get(key)
        if ref is None:
            raise UnknownCompany(ticker)
        return ref

    def search(self, query: str, limit: int = 8) -> list[CompanyRef]:
        """Best matches for a ticker or a piece of a name. One row per company."""
        q = query.strip().lower()
        if not q:
            return []
        self._load()

        def rank(r: CompanyRef) -> int | None:
            t, name = r.ticker.lower(), r.name.lower()
            if t == q:
                return 0
            if t.startswith(q):
                return 1
            if any(w.startswith(q) for w in re.split(r"[^a-z0-9]+", name)) or name.startswith(q):
                return 2
            return 3 if q in name else None

        scored = [(rank(r), i, r) for i, r in enumerate(self._rows)]
        out, seen = [], set()
        for _, _, r in sorted((s for s in scored if s[0] is not None), key=lambda s: (s[0], s[1])):
            if r.cik in seen:
                continue  # share classes of one company (GOOG and GOOGL)
            seen.add(r.cik)
            out.append(r)
            if len(out) == limit:
                break
        return out


# =========================================================================== storage
class Store(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...


class FileStore:
    """One JSON file per key under a directory. For local runs."""

    def __init__(self, root: Path = DATA / "ondemand"):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, key: str, value: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False))


class GcsStore:
    """One JSON object per key in a Cloud Storage bucket. For the deployed service, whose own
    disk is lost every time an instance stops."""

    def __init__(self, bucket: str):
        from google.cloud import storage

        self._bucket = storage.Client().bucket(bucket)

    def get(self, key: str) -> dict | None:
        from google.cloud.exceptions import NotFound

        try:
            return json.loads(self._bucket.blob(f"{key}.json").download_as_text())
        except NotFound:
            return None

    def put(self, key: str, value: dict) -> None:
        self._bucket.blob(f"{key}.json").upload_from_string(
            json.dumps(value, ensure_ascii=False), content_type="application/json")


# =========================================================================== analysis
def _spend_key(day: date) -> str:
    return f"spend/{day.isoformat()}"


TOTAL_KEY = "spend/total"


def spent_today(store: Store, day: date) -> float:
    return float((store.get(_spend_key(day)) or {}).get("usd", 0.0))


def spent_total(store: Store) -> float:
    return float((store.get(TOTAL_KEY) or {}).get("usd", 0.0))


class Analyser:
    def __init__(self, store: Store, client_factory: Callable[[], DecisionClient] | None = None,
                 daily_max_usd: float | None = None, total_max_usd: float | None = None):
        self.store = store
        self._client = client_factory or (lambda: DecisionClient(cap_usd=ONDEMAND_REQUEST_MAX_USD))
        self.daily_max_usd = ondemand_daily_max_usd() if daily_max_usd is None else daily_max_usd
        self.total_max_usd = ondemand_total_max_usd() if total_max_usd is None else total_max_usd
        self._lock = threading.Lock()

    def _read(self, ref: CompanyRef, filing: dict, today: date) -> Generator[dict, None, tuple[dict, float]]:
        """Read one filing that nobody has read yet. Yields what it is doing; returns what to
        store and what it cost."""
        acc = filing["accessionNumber"]
        yield {"step": "download", "id": acc, "filed": filing.get("filingDate")}
        try:
            docs = edgar.fetch_filing_docs(ref.cik, acc)
        except (httpx.HTTPStatusError, ValueError):
            return {"skip": "no_index"}, 0.0
        if not docs.exhibit_url:
            return {"skip": "no_exhibit"}, 0.0
        text = narrative_text(edgar.fetch_exhibit_html(docs.exhibit_url))
        if not text:
            return {"skip": "no_text"}, 0.0
        if spent_today(self.store, today) >= self.daily_max_usd or spent_total(self.store) >= self.total_max_usd:
            raise DailyBudgetReached()
        yield {"step": "model", "id": acc, "chars": len(text), "questions": N_QUESTIONS}
        # No yield from here on: a visitor who leaves must not cost a reading that was paid for.
        row = {"accessionNumber": acc, "cik": ref.cik, "ticker": ref.ticker, "sec_name": ref.name,
               "accepted_et": docs.accepted_et, "exhibit_url": docs.exhibit_url, "text": text}
        client = self._client()
        records, refused = R.score(pd.DataFrame([row]), themes=True, client=client)
        if acc in refused:
            return {"skip": refused[acc]}, client.spend.usd
        if not records:
            raise RuntimeError("the model did not answer")  # not stored: asked again next time
        read_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return records[0] | {"read_utc": read_utc}, client.spend.usd

    def _add_spend(self, today: date, usd: float) -> None:
        if usd <= 0:
            return
        with self._lock:
            self.store.put(_spend_key(today), {"usd": round(spent_today(self.store, today) + usd, 6)})
            self.store.put(TOTAL_KEY, {"usd": round(spent_total(self.store) + usd, 6)})

    def run(self, ref: CompanyRef, today: date | None = None) -> Iterator[dict]:
        """Analyse the company's latest results release and the one before it. Yields each step
        as it happens; the last event, ``done``, carries the result."""
        today = today or datetime.now(timezone.utc).date()
        started = time.monotonic()
        since = today - timedelta(days=ONDEMAND_LOOKBACK_DAYS)
        yield {"step": "edgar", "ticker": ref.ticker, "name": ref.name}
        try:
            filings = edgar.list_item_202_filings(ref.cik, since, today, fresh=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise NoResultsRelease(ref.ticker) from exc
            raise
        rows = filings.sort_values("acceptanceDateTime", ascending=False).to_dict("records") if len(filings) else []
        yield {"step": "filings", "count": len(rows), "since": since.isoformat()}

        found: list[dict] = []
        spent, fresh = 0.0, []
        for filing in rows[:ONDEMAND_MAX_FILINGS]:
            if len(found) == 2:
                break
            acc = filing["accessionNumber"]
            entry = self.store.get(f"analyses/{acc}")
            event = {"step": "read", "id": acc, "fresh": entry is None}
            if entry is None:
                began = time.monotonic()
                entry, cost = yield from self._read(ref, filing, today)
                self.store.put(f"analyses/{acc}", entry)
                self._add_spend(today, cost)
                spent += cost
                fresh.append(acc)
                event["seconds"] = round(time.monotonic() - began, 1)
            is_release = "skip" not in entry and entry["is_earnings"] >= RADAR_MIN_EARNINGS_PROB
            yield event | {"release": is_release, "skip": entry.get("skip"), "date": entry.get("date"),
                           "tokens": entry.get("tokens"), "read_utc": entry.get("read_utc")}
            if not is_release:
                continue
            if found and (pd.Timestamp(found[-1]["accepted"]) - pd.Timestamp(entry["accepted"])).days < RADAR_DEDUPE_DAYS:
                # Two filings for one release: the dataset keeps the first one filed, so do the same.
                found[-1] = entry
                continue
            found.append(entry)

        if not found:
            raise NoResultsRelease(ref.ticker)
        in_study = ref.ticker in COMPANIES
        yield {"step": "done", "result": {
            "company": {"ticker": ref.ticker, "name": COMPANIES[ref.ticker].name if in_study else ref.name,
                        "cik": ref.cik, "in_study": in_study},
            "latest": found[0],
            "previous": found[1] if len(found) > 1 else None,
            "model": DECIDER_MODEL,
            "questions": N_QUESTIONS,
            "fresh": fresh,  # the filings read by the model for this request
            "read_now": len(fresh),
            "spent_usd": round(spent, 5),
            "seconds": round(time.monotonic() - started, 1),
        }}

    def analyse(self, ref: CompanyRef, today: date | None = None) -> dict:
        """The result of ``run``, for callers that do not follow the steps."""
        event: dict = {}
        for event in self.run(ref, today):
            pass
        return event["result"]


__all__ = ["Analyser", "BudgetExceeded", "CompanyRef", "DailyBudgetReached", "Directory", "FileStore", "GcsStore",
           "NoResultsRelease", "Store", "UnknownCompany", "spent_today", "spent_total"]
