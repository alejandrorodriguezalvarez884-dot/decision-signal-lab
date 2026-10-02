"""Event timing is where look-ahead bias would come from, so it is tested case by case."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from jevsignal.events import build_events, locate_sessions, nyse_schedule

NY = "America/New_York"


@pytest.fixture(scope="module")
def sched():
    return nyse_schedule(date(2024, 6, 1), date(2025, 3, 31))


def _day(sched, i):
    return sched.index[i].date()


@pytest.mark.parametrize(
    "accepted, base, day0",
    [
        # pre-open release Thu 2024-10-31 07:30 -> reacts on Thu, base = Wed close
        ("2024-10-31 07:30", "2024-10-30", "2024-10-31"),
        # after-close release Thu 16:30 -> base Thu, reacts Fri
        ("2024-10-31 16:30", "2024-10-31", "2024-11-01"),
        # exactly at the close: close price is known, day-0 is next session
        ("2024-10-31 16:00", "2024-10-31", "2024-11-01"),
        # intraday Thu 11:00 -> base Wed close, day-0 Fri (first session OPENING after release)
        ("2024-10-31 11:00", "2024-10-30", "2024-11-01"),
        # Saturday release -> base Fri, day-0 Mon
        ("2024-11-02 10:00", "2024-11-01", "2024-11-04"),
        # day before Thanksgiving after close -> day-0 is the half-day Friday
        ("2024-11-27 17:00", "2024-11-27", "2024-11-29"),
        # half-day Friday 2024-11-29 closes 13:00; a 14:00 release reacts Monday
        ("2024-11-29 14:00", "2024-11-29", "2024-12-02"),
    ],
)
def test_locate_sessions(sched, accepted, base, day0):
    b, d0 = locate_sessions(pd.Timestamp(accepted).tz_localize(NY), sched)
    assert str(_day(sched, b)) == base
    assert str(_day(sched, d0)) == day0


def _synthetic_prices(sched, tickers=("AAA", "SPY", "XLK")):
    rng = np.random.default_rng(0)
    rows = []
    for t in tickers:
        px = 100.0
        for d in sched.index:
            o = px * (1 + rng.normal(0, 0.005))
            c = o * (1 + rng.normal(0, 0.01))
            rows.append({"date": d, "ticker": t, "open": o, "high": max(o, c), "low": min(o, c), "close": c, "volume": 1e6})
            px = c
    return pd.DataFrame(rows)


def test_build_events_no_lookahead_and_returns(sched):
    prices = _synthetic_prices(sched)
    filings = pd.DataFrame([{
        "accessionNumber": "0000000000-24-000001", "cik": 1, "sec_name": "AAA INC", "sic": 3572,
        "accepted_et": pd.Timestamp("2024-10-31 16:30").tz_localize(NY), "price_ticker": "AAA",
    }])
    ev = build_events(filings, prices).iloc[0]
    assert ev["drop_reason"] is None
    assert ev["entry_open_utc"] > ev["accepted_et"].tz_convert("UTC")
    assert ev["entry_session"] == pd.Timestamp("2024-11-04")
    c = prices.set_index(["ticker", "date"])
    r0 = c.loc[("AAA", pd.Timestamp("2024-11-01")), "close"] / c.loc[("AAA", pd.Timestamp("2024-10-31")), "close"] - 1
    m0 = c.loc[("SPY", pd.Timestamp("2024-11-01")), "close"] / c.loc[("SPY", pd.Timestamp("2024-10-31")), "close"] - 1
    assert ev["r0_abn"] == pytest.approx(r0 - m0)
    # forward 5: open of entry (11-04) to close of 4 sessions later (11-08)
    f = c.loc[("AAA", pd.Timestamp("2024-11-08")), "close"] / c.loc[("AAA", pd.Timestamp("2024-11-04")), "open"] - 1
    fm = c.loc[("SPY", pd.Timestamp("2024-11-08")), "close"] / c.loc[("SPY", pd.Timestamp("2024-11-04")), "open"] - 1
    assert ev["fwd_abn_5"] == pytest.approx(f - fm)
    assert ev["sector_etf"] == "XLK"
    assert ev["split"] == "design"


def test_forward_return_missing_when_future_not_available(sched):
    prices = _synthetic_prices(sched)
    prices = prices[prices["date"] <= pd.Timestamp("2025-03-10")]
    filings = pd.DataFrame([{
        "accessionNumber": "x", "cik": 1, "sec_name": "AAA INC", "sic": 3572,
        "accepted_et": pd.Timestamp("2025-02-27 07:00").tz_localize(NY), "price_ticker": "AAA",
    }])
    ev = build_events(filings, prices).iloc[0]
    assert np.isfinite(ev["fwd_abn_5"])
    assert np.isnan(ev["fwd_abn_60"])
    assert ev["split"] == "holdout"
