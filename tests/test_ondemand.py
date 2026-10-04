import json
from datetime import date

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from decisionsignal import ondemand as O
from decisionsignal.api import RateLimiter, create_app
from decisionsignal.client import Cache, DecisionClient
from decisionsignal.edgar import FilingDocs
from decisionsignal.questions import THEME_QUESTIONS
from test_radar import core_response, theme_response

NY = "America/New_York"
SEC_ROWS = [
    {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    {"cik_str": 1000001, "ticker": "APLD", "title": "Applied Digital Corp."},
    {"cik_str": 1000002, "ticker": "ZETA", "title": "Zeta Apple Farms Inc"},
    {"cik_str": 1000003, "ticker": "BRK-B", "title": "Berkshire Hathaway Inc"},
]
ZETA = O.CompanyRef("ZETA", 1000002, "Zeta Apple Farms Inc")


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value


@pytest.fixture
def directory():
    return O.Directory(fetch=lambda: SEC_ROWS)


def test_directory_ranks_ticker_before_name_and_merges_share_classes(directory):
    assert [r.ticker for r in directory.search("ap")] == ["APLD", "AAPL", "ZETA"]
    assert [r.ticker for r in directory.search("apple")] == ["AAPL", "ZETA"]
    assert [r.ticker for r in directory.search("alphabet")] == ["GOOGL"]
    assert directory.search("   ") == []
    assert directory.get("aapl").cik == 320193 and directory.get("BRK.B").ticker == "BRK-B"


@pytest.mark.parametrize("bad", ["", "NOPE", "../etc", "A B", "DROP TABLE"])
def test_directory_rejects_unknown_or_malformed_tickers(directory, bad):
    with pytest.raises(O.UnknownCompany):
        directory.get(bad)


def _filings(*rows):
    return pd.DataFrame([{"accessionNumber": acc, "acceptanceDateTime": when} for acc, when in rows])


@pytest.fixture
def edgar_stub(monkeypatch):
    """EDGAR for one company: four Item 2.02 filings, the second newest being slides."""
    listing = _filings(("f-aug", "2026-08-05T16:10:00"), ("f-aug-slides", "2026-08-06T09:00:00"),
                       ("f-may", "2026-05-06T16:10:00"), ("f-feb", "2026-02-04T16:10:00"))
    accepted = {"f-aug": "2026-08-05 16:10", "f-aug-slides": "2026-08-06 09:00",
                "f-may": "2026-05-06 16:10", "f-feb": "2026-02-04 16:10"}
    monkeypatch.setattr(O.edgar, "list_item_202_filings", lambda cik, start, end, fresh=False: listing)
    monkeypatch.setattr(O.edgar, "fetch_filing_docs", lambda cik, acc: FilingDocs(
        pd.Timestamp(accepted[acc], tz=NY), f"https://www.sec.gov/{acc}.htm", "EX-99.1"))
    monkeypatch.setattr(O.edgar, "fetch_exhibit_html", lambda url: (
        "<p>Slides for the quarter. " + "Chart. " * 40 + "</p>" if "slides" in url
        else f"<p>The company reported quarterly results in filing {url[-9:-4]}. Revenue grew and guidance was "
             "raised. " + "More detail. " * 40 + "</p>"))


def _analyser(tmp_path, store, calls, known=None, daily=1.0, total=100.0):
    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if set(body["questions"]) == set(THEME_QUESTIONS):
            return httpx.Response(200, json=theme_response(ai=0.8))
        slides = "Slides" in body["state"]["press_release"]
        return httpx.Response(200, json=core_response("raised", is_earnings=0.1 if slides else 0.95))

    def factory():
        return DecisionClient(cache=Cache(tmp_path / "c.sqlite"), transport=httpx.MockTransport(handler),
                              cap_usd=1.0, api_key="test")

    return O.Analyser(store, known=known or {}, client_factory=factory, daily_max_usd=daily, total_max_usd=total)


def test_analyse_finds_latest_and_previous_and_reads_each_filing_once(tmp_path, edgar_stub):
    store, calls = MemoryStore(), []
    a = _analyser(tmp_path, store, calls)
    out = a.analyse(ZETA, today=date(2026, 10, 4))
    assert out["company"] == {"ticker": "ZETA", "name": "Zeta Apple Farms Inc", "cik": 1000002, "in_study": False}
    assert out["latest"]["id"] == "f-aug" and out["previous"]["id"] == "f-may"
    assert out["latest"]["ticker"] == "ZETA" and out["latest"]["themes"]["ai"] == 0.8
    assert out["read_now"] == 3 and out["spent_usd"] > 0  # slides, August, May; February never needed
    assert len(calls) == 6
    for body in calls:  # text only, identity masked
        assert set(body["state"]) == {"press_release"} and "Zeta" not in body["state"]["press_release"]
    assert store.get("analyses/f-aug-slides")["is_earnings"] == 0.1
    assert O.spent_today(store, date(2026, 10, 4)) == pytest.approx(out["spent_usd"], abs=1e-5)
    assert O.spent_total(store) == pytest.approx(out["spent_usd"], abs=1e-5)

    again = a.analyse(ZETA, today=date(2026, 10, 4))
    assert again["latest"]["id"] == "f-aug" and again["read_now"] == 0 and again["spent_usd"] == 0
    assert len(calls) == 6


def test_analyse_uses_the_published_dataset_without_calling_the_model(tmp_path, edgar_stub):
    known = {"f-aug": {"id": "f-aug", "accepted": "2026-08-05T16:10:00-04:00", "is_earnings": 0.99},
             "f-aug-slides": {"skip": "not_earnings"},
             "f-may": {"id": "f-may", "accepted": "2026-05-06T16:10:00-04:00", "is_earnings": 0.99}}
    calls = []
    out = _analyser(tmp_path, MemoryStore(), calls, known=known).analyse(ZETA, today=date(2026, 10, 4))
    assert (out["latest"]["id"], out["previous"]["id"], out["read_now"], calls) == ("f-aug", "f-may", 0, [])


def test_analyse_stops_at_the_daily_budget_but_serves_what_is_stored(tmp_path, edgar_stub):
    store, calls = MemoryStore(), []
    store.put("spend/2026-10-04", {"usd": 0.5})
    a = _analyser(tmp_path, store, calls, daily=0.5)
    with pytest.raises(O.DailyBudgetReached):
        a.analyse(ZETA, today=date(2026, 10, 4))
    assert calls == []
    out = a.analyse(ZETA, today=date(2026, 10, 5))  # a new day
    assert out["latest"]["id"] == "f-aug"


def test_analyse_stops_at_the_lifetime_budget(tmp_path, edgar_stub):
    store, calls = MemoryStore(), []
    store.put("spend/total", {"usd": 4.0})
    a = O.Analyser(store, known={}, client_factory=lambda: None, daily_max_usd=1.0, total_max_usd=4.0)
    with pytest.raises(O.DailyBudgetReached):
        a.analyse(ZETA, today=date(2026, 10, 9))
    assert calls == []


def test_analyse_without_filings_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(O.edgar, "list_item_202_filings", lambda *a, **k: pd.DataFrame())
    with pytest.raises(O.NoResultsRelease):
        _analyser(tmp_path, MemoryStore(), []).analyse(ZETA, today=date(2026, 10, 4))


def test_file_store_roundtrip(tmp_path):
    s = O.FileStore(tmp_path)
    assert s.get("analyses/x") is None
    s.put("analyses/x", {"a": 1})
    assert s.get("analyses/x") == {"a": 1}


def test_rate_limiter_counts_per_address():
    r = RateLimiter(limit=2)
    assert r.allow("a") and r.allow("a") and not r.allow("a") and r.allow("b")


def test_api_routes(tmp_path, edgar_stub, directory):
    site = tmp_path / "site"
    (site / "trends").mkdir(parents=True)
    (site / "index.html").write_text("<h1>home</h1>")
    (site / "trends" / "index.html").write_text("<h1>trends</h1>")
    app = create_app(analyser=_analyser(tmp_path, MemoryStore(), []), directory=directory, static_dir=str(site))
    c = TestClient(app)
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/api/companies", params={"q": "apple"}).json()["companies"][0] == {"ticker": "AAPL", "name": "Apple Inc."}
    assert c.get("/api/companies").status_code == 422
    ok = c.get("/api/analysis/zeta")
    assert ok.status_code == 200 and ok.json()["latest"]["id"] == "f-aug"
    assert c.get("/api/analysis/NOPE").status_code == 404
    assert "home" in c.get("/").text and "trends" in c.get("/trends/").text
    assert c.get("/openapi.json").status_code == 404
