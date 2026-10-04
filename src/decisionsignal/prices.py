"""Daily adjusted OHLC prices from Yahoo Finance (via yfinance).

Limitations (documented in METHODOLOGY): unofficial API, adjusted history can be revised,
delisted symbols are often missing (residual survivorship bias, measured in coverage reports).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from .config import BENCHMARK, PATHS

SECTOR_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


def yahoo_symbol(ticker: str) -> str:
    return ticker.upper().replace(".", "-")


def download(tickers: list[str], start: date, end: date, batch: int = 100) -> pd.DataFrame:
    """Long frame: date, ticker, open, high, low, close, volume (split/dividend adjusted)."""
    syms = sorted({yahoo_symbol(t) for t in tickers})
    frames = []
    for i in range(0, len(syms), batch):
        chunk = syms[i : i + batch]
        raw = yf.download(
            chunk,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        if raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):
            raw.columns = pd.MultiIndex.from_product([[chunk[0]], raw.columns])
        long = raw.stack(level=0, future_stack=True).reset_index()
        long.columns = [str(c).lower() for c in long.columns]
        long = long.rename(columns={"level_1": "ticker", "price": "ticker"})
        frames.append(long)
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["open", "close"])
    df = df[(df["open"] > 0) & (df["close"] > 0)]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return df[["date", "ticker", "open", "high", "low", "close", "volume"]].sort_values(["ticker", "date"])


def build_prices(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    all_syms = list(tickers) + [BENCHMARK, *SECTOR_ETFS]
    # Pad the start for the pre-event volatility / momentum lookbacks.
    df = download(all_syms, start - timedelta(days=150), end)
    df.to_parquet(PATHS.prices, index=False)
    return df
