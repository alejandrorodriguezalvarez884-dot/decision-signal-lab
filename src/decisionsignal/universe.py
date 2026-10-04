"""The study universe (S&P 100 as of December 2020), its point-in-time S&P 500 membership and
the ticker -> SEC CIK mapping.

Membership: github.com/fja05680/sp500 (MIT), one row per membership spell
(ticker, start_date, end_date). Using spells instead of today's constituents removes the
grossest survivorship bias. The ticker -> CIK map comes from SEC's company_tickers.json, which
only knows *current* tickers, so companies that were acquired or delisted are usually missing.
That residual survivorship bias is measured (coverage report) and documented, not hidden.
"""

from __future__ import annotations

import io
import json
from datetime import date

import pandas as pd

from .config import PATHS, SP100_DEC_2020, STUDY_START, sec_user_agent
from .http import cached_get

MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def load_membership() -> pd.DataFrame:
    raw = cached_get(MEMBERSHIP_URL)
    PATHS.sp500_membership.write_bytes(raw)
    df = pd.read_csv(io.BytesIO(raw), parse_dates=["start_date", "end_date"])
    df["ticker"] = df["ticker"].str.strip().str.upper()
    return df


def load_sec_tickers() -> pd.DataFrame:
    raw = cached_get(SEC_TICKERS_URL, headers={"User-Agent": sec_user_agent()})
    PATHS.sec_tickers.write_bytes(raw)
    rows = json.loads(raw).values()
    df = pd.DataFrame(rows).rename(columns={"cik_str": "cik", "title": "company"})
    df["ticker"] = df["ticker"].str.upper()
    return df[["ticker", "cik", "company"]]


# Historical symbol -> current symbol, for renames inside the study window. Without these the
# pre-rename spell would not map to a CIK and its events would silently drop out.
TICKER_RENAMES = {
    "FB": "META",
    "ANTM": "ELV",
    "FISV": "FI",
    "PEAK": "DOC",
    "WLTW": "WTW",
    "BLL": "BALL",
    "RE": "EG",
    "FLT": "CPAY",
    "SQ": "XYZ",
    "ABC": "COR",
    "PKI": "RVTY",
    "DISCA": "WBD",
    "DISCK": "WBD",
    "NLOK": "GEN",
    "ADS": "BFH",
    "COG": "CTRA",
    "BK": "BNY",
}


def normalize_ticker(t: str) -> str:
    """SEC and the membership file use dots or dashes for share classes; unify on dashes."""
    t = t.upper().replace(".", "-")
    return TICKER_RENAMES.get(t, t)


def spells_overlapping(membership: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    m = membership.copy()
    m["end_date"] = m["end_date"].fillna(pd.Timestamp.max.normalize())
    return m[(m["start_date"] <= e) & (m["end_date"] >= s)]


def restrict_to_sp100(spells: pd.DataFrame) -> pd.DataFrame:
    """Keep the spells of the companies in the fixed S&P 100 list, under any ticker they have
    used (the list says FB; the later META spell belongs to the same company)."""
    wanted = {normalize_ticker(t) for t in SP100_DEC_2020}
    return spells[spells["ticker"].map(normalize_ticker).isin(wanted)]


def build_universe(end: date | None = None) -> pd.DataFrame:
    """One row per membership spell in the study window, with CIK when it can be mapped."""
    end = end or date.today()
    spells = restrict_to_sp100(spells_overlapping(load_membership(), STUDY_START, end)).copy()
    spells["key"] = spells["ticker"].map(normalize_ticker)
    sec = load_sec_tickers()
    sec["key"] = sec["ticker"].map(normalize_ticker)
    sec = sec.drop_duplicates("key").rename(columns={"ticker": "price_ticker"})
    uni = spells.merge(sec[["key", "cik", "company", "price_ticker"]], on="key", how="left")
    uni = uni.drop(columns="key")
    uni["cik"] = uni["cik"].astype("Int64")
    uni.to_parquet(PATHS.universe, index=False)
    return uni


def coverage_report(uni: pd.DataFrame) -> dict:
    mapped = uni["cik"].notna()
    return {
        "companies": int(uni["cik"].nunique()),
        "spells": int(len(uni)),
        "mapped_to_cik": int(mapped.sum()),
        "unmapped_tickers": sorted(uni.loc[~mapped, "ticker"].unique().tolist()),
    }


def is_member(uni: pd.DataFrame, cik: int, on: pd.Timestamp) -> bool:
    rows = uni[uni["cik"] == cik]
    end = rows["end_date"].fillna(pd.Timestamp.max.normalize())
    return bool(((rows["start_date"] <= on) & (end >= on)).any())
