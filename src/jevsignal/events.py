"""Event timing and returns. This module is where look-ahead would sneak in, so it is explicit.

For a release accepted by EDGAR at time ``t`` (US Eastern):

    base session   = last NYSE session whose close is at or before t
    day-0 session  = first NYSE session whose open is strictly after t
    reaction R0    = close(day-0) / close(base) - 1, minus the same for the benchmark
    entry          = open of the session after day-0  (the decision is made overnight, after the
                     full day-0 reaction is known; no price at or before day-0 close is "traded")
    forward h      = close(entry + h - 1) / open(entry) - 1, minus the benchmark over the same window

Everything used to describe the event to Jev (R0, its size relative to the stock's normal
volatility, momentum) ends at day-0 close, strictly before entry.
"""

from __future__ import annotations

from datetime import date, timedelta

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .prices import yahoo_symbol
from .config import (
    BENCHMARK,
    HOLDOUT_START,
    HORIZONS,
    MOMENTUM_LOOKBACK,
    SIC_TO_SECTOR_ETF,
    VOL_LOOKBACK,
)

NY = "America/New_York"


def nyse_schedule(start: date, end: date) -> pd.DataFrame:
    cal = xcals.get_calendar("XNYS", start=pd.Timestamp(start), end=pd.Timestamp(end))
    sched = cal.schedule.loc[:, ["open", "close"]].copy()
    sched.index = pd.DatetimeIndex(sched.index).tz_localize(None).normalize()
    return sched


def locate_sessions(accepted: pd.Timestamp, sched: pd.DataFrame) -> tuple[int, int] | None:
    """Return positional indexes (base, day0) in ``sched`` for an acceptance timestamp."""
    acc_utc = accepted.tz_convert("UTC")
    base = int(sched["close"].searchsorted(acc_utc, side="right")) - 1
    day0 = int(sched["open"].searchsorted(acc_utc, side="right"))
    if base < 0 or day0 >= len(sched):
        return None
    return base, day0


def sector_etf_for_sic(sic: object) -> str | None:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    for lo, hi, etf in SIC_TO_SECTOR_ETF:
        if lo <= code <= hi:
            return etf
    return None


class PriceBook:
    """Fast lookups of open/close by (ticker, session date)."""

    def __init__(self, prices: pd.DataFrame):
        self.open = prices.pivot(index="date", columns="ticker", values="open").sort_index()
        self.close = prices.pivot(index="date", columns="ticker", values="close").sort_index()
        self.dollar_vol = (prices["close"] * prices["volume"]).groupby(
            [prices["date"], prices["ticker"]]
        ).first().unstack().sort_index()

    def has(self, ticker: str) -> bool:
        return ticker in self.close.columns

    def px(self, kind: str, ticker: str, day: pd.Timestamp) -> float:
        frame = self.open if kind == "open" else self.close
        try:
            v = frame.at[day, ticker]
        except KeyError:
            return np.nan
        return float(v) if pd.notna(v) else np.nan


def _ret(book: PriceBook, ticker: str, d_from: pd.Timestamp, kind_from: str, d_to: pd.Timestamp) -> float:
    a = book.px(kind_from, ticker, d_from)
    b = book.px("close", ticker, d_to)
    return b / a - 1 if a and not np.isnan(a) and not np.isnan(b) else np.nan


def _pre_event_stats(book: PriceBook, ticker: str, sessions: pd.DatetimeIndex, base_i: int) -> dict:
    lo = max(0, base_i - max(VOL_LOOKBACK, MOMENTUM_LOOKBACK))
    window = sessions[lo : base_i + 1]
    if ticker not in book.close.columns:
        return {"vol_daily": np.nan, "momentum": np.nan, "log_dollar_vol": np.nan}
    stock = book.close[ticker].reindex(window)
    bench = book.close[BENCHMARK].reindex(window)
    abn = (stock.pct_change() - bench.pct_change()).dropna()
    vol = abn.tail(VOL_LOOKBACK).std() if len(abn) >= VOL_LOOKBACK // 2 else np.nan
    mom_window = window[-(MOMENTUM_LOOKBACK + 1) :]
    s0, s1 = book.close[ticker].get(mom_window[0]), book.close[ticker].get(mom_window[-1])
    b0, b1 = book.close[BENCHMARK].get(mom_window[0]), book.close[BENCHMARK].get(mom_window[-1])
    momentum = (s1 / s0 - 1) - (b1 / b0 - 1) if all(pd.notna(x) for x in (s0, s1, b0, b1)) else np.nan
    dv = book.dollar_vol[ticker].reindex(window[-20:]).mean() if ticker in book.dollar_vol else np.nan
    return {
        "vol_daily": vol,
        "momentum": momentum,
        "log_dollar_vol": float(np.log(dv)) if dv and dv > 0 else np.nan,
    }


def build_events(filings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if filings.empty:
        return filings
    start = filings["accepted_et"].min().date() - timedelta(days=200)
    end = max(prices["date"].max().date(), filings["accepted_et"].max().date()) + timedelta(days=10)
    sched = nyse_schedule(start, end)
    sessions = sched.index
    book = PriceBook(prices)
    last_price_day = prices["date"].max()

    rows = []
    for f in filings.to_dict("records"):
        ticker = yahoo_symbol(f["price_ticker"]) if isinstance(f["price_ticker"], str) else None
        rec = {k: f[k] for k in ("accessionNumber", "cik", "sec_name", "sic", "accepted_et", "price_ticker")}
        loc = locate_sessions(f["accepted_et"], sched)
        if loc is None or not isinstance(ticker, str) or not book.has(ticker):
            rec["drop_reason"] = "no_prices" if loc else "outside_calendar"
            rows.append(rec)
            continue
        base_i, day0_i = loc
        entry_i = day0_i + 1
        if entry_i >= len(sessions):
            rec["drop_reason"] = "no_entry_session_yet"
            rows.append(rec)
            continue
        base, day0, entry = sessions[base_i], sessions[day0_i], sessions[entry_i]
        entry_open_utc = sched["open"].iloc[entry_i]
        assert entry_open_utc > f["accepted_et"].tz_convert("UTC"), "look-ahead: entry before publication"
        assert entry > day0 >= base

        sector = sector_etf_for_sic(f.get("sic"))
        r0 = _ret(book, ticker, base, "close", day0)
        r0_mkt = _ret(book, BENCHMARK, base, "close", day0)
        r0_sec = _ret(book, sector, base, "close", day0) if sector else np.nan
        stats = _pre_event_stats(book, ticker, sessions, base_i)
        k = day0_i - base_i  # sessions in the reaction window (1 normally, 2 if released intraday)
        rec.update(
            base_session=base,
            day0_session=day0,
            entry_session=entry,
            entry_open_utc=entry_open_utc,
            reaction_sessions=k,
            sector_etf=sector,
            r0_raw=r0,
            r0_abn=r0 - r0_mkt,
            r0_sec_abn=r0 - r0_sec if sector else np.nan,
            r0_z=(r0 - r0_mkt) / (stats["vol_daily"] * np.sqrt(k)) if stats["vol_daily"] else np.nan,
            **stats,
        )
        for h in HORIZONS:
            exit_i = entry_i + h - 1
            if exit_i >= len(sessions) or sessions[exit_i] > last_price_day:
                rec[f"fwd_abn_{h}"] = rec[f"fwd_sec_abn_{h}"] = np.nan
                continue
            exit_ = sessions[exit_i]
            fr = _ret(book, ticker, entry, "open", exit_)
            fm = _ret(book, BENCHMARK, entry, "open", exit_)
            fs = _ret(book, sector, entry, "open", exit_) if sector else np.nan
            rec[f"fwd_abn_{h}"] = fr - fm
            rec[f"fwd_sec_abn_{h}"] = fr - fs if sector else np.nan
        rec["drop_reason"] = None if pd.notna(rec["r0_abn"]) else "missing_reaction_prices"
        rows.append(rec)

    ev = pd.DataFrame(rows)
    ev["event_date"] = ev["accepted_et"].dt.tz_convert(NY).dt.tz_localize(None).dt.normalize()
    ev["split"] = np.where(ev["event_date"] >= pd.Timestamp(HOLDOUT_START), "holdout", "design")
    return ev


def dedupe_quarterly(ev: pd.DataFrame, min_gap_days: int = 20) -> pd.DataFrame:
    """Keep the first Item 2.02 filing per company when several land within ``min_gap_days``."""
    ev = ev.sort_values(["cik", "accepted_et"])
    keep, last = [], {}
    for idx, row in ev.iterrows():
        prev = last.get(row["cik"])
        if prev is None or (row["accepted_et"] - prev).days >= min_gap_days:
            keep.append(idx)
            last[row["cik"]] = row["accepted_et"]
    return ev.loc[keep].sort_values("accepted_et").reset_index(drop=True)
