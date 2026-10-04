"""Paths, environment and study-wide constants.

Every number that defines the study design lives here or in ``questions.py`` so a reviewer can
audit the whole design from two files.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
CACHE = DATA / "cache"
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
RADAR = ROOT / "radar"  # the published dataset; committed, unlike data/

for _p in (RAW, INTERIM, CACHE, RESULTS):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- study window
STUDY_START = date(2021, 1, 1)
# Events from HOLDOUT_START onward are never scored until the pre-registration is locked.
HOLDOUT_START = date(2025, 1, 1)

# --------------------------------------------------------------------------- universe
# The study covers the S&P 100 as it stood just before the study window: the constituents on
# 21 December 2020 (table in en.wikipedia.org/wiki/S%26P_100, revision 996842773, taken from the
# iShares OEF holdings). The list is fixed at the start so that no company is picked by how it
# did afterwards. 101 symbols for 100 companies (Alphabet has two share classes). A company
# still has to be in the S&P 500 on the day of the event.
SP100_DEC_2020 = tuple("""
    AAPL ABBV ABT ACN ADBE AIG ALL AMGN AMT AMZN AXP BA BAC BIIB BK BKNG BLK BMY BRK.B C CAT
    CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DD DHR DIS DOW DUK EMR EXC F FB FDX GD GE
    GILD GM GOOG GOOGL GS HD HON IBM INTC JNJ JPM KHC KMI KO LLY LMT LOW MA MCD MDLZ MDT MET
    MMM MO MRK MS MSFT NEE NFLX NKE NVDA ORCL PEP PFE PG PM PYPL QCOM RTX SBUX SLB SO SPG T
    TGT TMO TSLA TXN UNH UNP UPS USB V VZ WBA WFC WMT XOM
""".split())

# --------------------------------------------------------------------------- returns
BENCHMARK = "SPY"
# Forward horizons in trading sessions, counted from the entry session (entry = h day 1).
HORIZONS = (1, 5, 20, 60)
PRIMARY_HORIZON = 20
# Pre-event window used to measure each stock's normal daily abnormal-return volatility.
VOL_LOOKBACK = 60
MOMENTUM_LOOKBACK = 60

# Approximate SIC -> SPDR sector ETF map, for the secondary (sector-adjusted) benchmark.
# (low, high inclusive, etf). First match wins. Coarse by design; see docs/METHODOLOGY.md.
SIC_TO_SECTOR_ETF: tuple[tuple[int, int, str], ...] = (
    (1300, 1399, "XLE"),  # oil and gas extraction
    (1000, 1499, "XLB"),  # other mining
    (2830, 2836, "XLV"),  # pharma
    (2900, 2999, "XLE"),  # petroleum refining
    (3570, 3579, "XLK"),  # computers
    (3600, 3699, "XLK"),  # electronics
    (3670, 3679, "XLK"),
    (3840, 3851, "XLV"),  # medical instruments
    (4800, 4899, "XLC"),  # communications
    (4900, 4999, "XLU"),  # utilities
    (6000, 6499, "XLF"),  # finance, insurance
    (6500, 6553, "XLRE"),
    (6798, 6798, "XLRE"),  # REITs
    (7370, 7379, "XLK"),  # software / services
    (8000, 8099, "XLV"),  # health services
    (2000, 2199, "XLP"),  # food, tobacco
    (5400, 5499, "XLP"),  # food stores
    (5000, 5999, "XLY"),  # wholesale / retail
    (2800, 2899, "XLB"),  # chemicals
    (3700, 3799, "XLI"),  # transport equipment
    (4000, 4799, "XLI"),  # transportation
    (1500, 1799, "XLI"),  # construction
    (3400, 3599, "XLI"),  # machinery
    (2200, 3999, "XLI"),  # other manufacturing
    (7000, 8999, "XLY"),  # services
)

# --------------------------------------------------------------------------- decision model
# Perplexity Decisions API. Source for the numbers below: docs.perplexity.ai/docs/decisions/quickstart,
# 2026-10.
DECIDER_URL = "https://api.perplexity.ai/v1/decisions"
# The only model the Decisions API serves; there is no moving alias.
DECIDER_MODEL = "pplx-decider-v1-27b"
# USD per input token (output tokens are free).
DECIDER_PRICE_PER_INPUT_TOKEN = 0.04 / 1_000_000
# Docs: under 262,144 input tokens per request. Keep a wide margin; tokens estimated as chars/3.5.
MAX_STATE_CHARS = 60_000
CHARS_PER_TOKEN_ESTIMATE = 3.5
DECIDER_CONCURRENCY = 8
DECIDER_MAX_RPS = 8  # documented limit is 10 rps per organization; stay below it


def perplexity_api_key() -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PERPLEXITY_API_KEY is not set. Put it in .env or export it.")
    return key


def model_release_date() -> date | None:
    """Release date of the pinned model (from its model card); events after it are reported
    separately because the model cannot have seen their outcomes."""
    v = os.environ.get("DECIDER_RELEASE_DATE", "").strip()
    return date.fromisoformat(v) if v else None


def max_usd() -> float:
    return float(os.environ.get("DECIDER_MAX_USD", "1.00"))


def total_max_usd() -> float:
    """Ceiling on everything the project has ever spent on the API, cached responses included."""
    return float(os.environ.get("DECIDER_TOTAL_MAX_USD", "10.00"))


# --------------------------------------------------------------------------- sampling (cost control)
# Share of events also sent without identity masking (the raw variants only serve the
# memorization check). Membership comes from a hash of the filing number, so it is fixed in
# advance and does not depend on the data or its order.
RAW_SAMPLE_FRACTION = 0.15
SAMPLE_SEED = "decisionsignal-2026-10"


def in_sample(kind: str, key: object, fraction: float) -> bool:
    digest = hashlib.sha256(f"{SAMPLE_SEED}:{kind}:{key}".encode()).hexdigest()
    return int(digest[:8], 16) / 0x1_0000_0000 < fraction


def in_raw_sample(accession: str) -> bool:
    return in_sample("raw", accession, RAW_SAMPLE_FRACTION)


# --------------------------------------------------------------------------- radar
# A filing is published only if the model itself reads it as a results release.
RADAR_MIN_EARNINGS_PROB = 0.5
# Several Item 2.02 filings by one company within this many days count as one release (the first).
RADAR_DEDUPE_DAYS = 20
# How far back each update looks for filings it has not seen.
RADAR_LOOKBACK_DAYS = 45
# A theme counts as present in a release from this probability up.
RADAR_THEME_THRESHOLD = 0.5
RADAR_LATEST = 40


# --------------------------------------------------------------------------- SEC
SEC_MAX_RPS = 8  # SEC fair-access policy allows 10 requests/second


def sec_user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. EDGAR requires a descriptive User-Agent with a contact "
            "email, e.g. 'DecisionSignalLab research you@example.com'. Set it in .env."
        )
    return ua


@dataclass(frozen=True)
class Paths:
    sp500_membership: Path = RAW / "sp500_membership.csv"
    sec_tickers: Path = RAW / "sec_company_tickers.json"
    universe: Path = INTERIM / "universe.parquet"
    filings: Path = INTERIM / "filings.parquet"
    texts: Path = INTERIM / "texts.parquet"
    prices: Path = INTERIM / "prices.parquet"
    events: Path = INTERIM / "events.parquet"
    answers: Path = INTERIM / "answers.parquet"
    features: Path = INTERIM / "features.parquet"
    decision_cache: Path = CACHE / "decision_cache.sqlite"
    http_cache: Path = CACHE / "http"
    lock: Path = DOCS / "PREREGISTRATION.lock.json"
    radar_releases: Path = RADAR / "releases.json"
    radar_summary: Path = RADAR / "summary.json"


PATHS = Paths()
