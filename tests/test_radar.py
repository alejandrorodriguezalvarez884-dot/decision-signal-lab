import dataclasses
import json
from datetime import date

import httpx
import pandas as pd
import pytest

from decisionsignal import radar as R
from decisionsignal.client import Cache, DecisionClient
from decisionsignal.questions import TEXT_QUESTIONS, THEME_QUESTIONS

NY = "America/New_York"


def core_response(guidance="raised", is_earnings=0.97, strength=3.0):
    probs = {k: 0.02 for k in TEXT_QUESTIONS["guidance"]["criteria"]}
    probs[guidance] = 0.88
    answers = {}
    for qid, q in TEXT_QUESTIONS.items():
        if q["type"] == "noul":
            answers[qid] = {"type": "noul", "noul": is_earnings if qid == "is_earnings_release" else 0.25}
        elif q["type"] == "score":
            n = len(q["criteria"])
            answers[qid] = {"type": "score", "score": strength if qid == "results_strength" else 1.0,
                            "confidence": 0.8, "probabilities": {str(i): 1 / n for i in range(n)}}
    answers["guidance"] = {"type": "choice", "choice": guidance, "confidence": 0.8, "probabilities": probs}
    return {"model": "pplx-decider-v1-27b", "answers": answers, "usage": {"input_tokens": 800}}


def theme_response(**probs):
    return {"model": "pplx-decider-v1-27b",
            "answers": {k: {"type": "noul", "noul": probs.get(k, 0.1)} for k in THEME_QUESTIONS},
            "usage": {"input_tokens": 400}}


def filing(acc="0000320193-26-000001", cik=320193, when="2026-07-30 16:30", text="Revenue grew. Guidance raised."):
    return {"accessionNumber": acc, "cik": cik, "sec_name": "Apple Inc.",
            "accepted_et": pd.Timestamp(when, tz=NY), "exhibit_url": "https://www.sec.gov/x.htm", "text": text}


def record(acc, ticker="AAPL", when="2026-07-30", guidance="raised", is_earnings=0.97, themes=None):
    return {"id": acc, "ticker": ticker, "accepted": f"{when}T16:30:00-04:00", "date": when,
            "quarter": f"{when[:4]}Q{(int(when[5:7]) - 1) // 3 + 1}", "url": "u", "exhibit": "e",
            "is_earnings": is_earnings, "guidance": guidance,
            "guidance_p": {k: (0.9 if k == guidance else 0.01) for k in R.GUIDANCE_CLASSES},
            **{f: 0.5 for f in R.SCORE_FIELDS}, "themes": themes or {}, "tokens": 1000}


@pytest.fixture
def radar_dir(tmp_path, monkeypatch):
    paths = dataclasses.replace(R.PATHS, radar_releases=tmp_path / "releases.json",
                                radar_summary=tmp_path / "summary.json")
    monkeypatch.setattr(R, "PATHS", paths)
    return tmp_path


def test_release_record_fields():
    rec = R.release_record(filing(), core_response("raised", strength=3.0), theme_response(tariffs=0.9))
    assert rec["ticker"] == "AAPL" and rec["date"] == "2026-07-30" and rec["quarter"] == "2026Q3"
    assert rec["url"].endswith("/000032019326000001/0000320193-26-000001-index.htm")
    assert rec["guidance"] == "raised" and rec["guidance_p"]["raised"] == 0.88
    assert rec["results_strength"] == 0.75  # score 3 of 0..4
    assert rec["themes"]["tariffs"] == 0.9 and set(rec["themes"]) == set(THEME_QUESTIONS)
    assert rec["tokens"] == 1200
    assert "naive_reaction" not in rec


def test_release_record_without_themes_and_on_model_error():
    rec = R.release_record(filing(), core_response(), None)
    assert rec["themes"] == {} and rec["tokens"] == 800
    assert R.release_record(filing(), {"error": "retries_exhausted"}, None) is None
    assert R.release_record(filing(), core_response(), {"error": "retries_exhausted"}) is None


def test_requests_carry_text_only():
    core, themes = R.requests_for(filing(text="Apple Inc. (NASDAQ: AAPL) raised guidance on July 30, 2026."))
    for p in (core, themes):
        assert set(p["state"]) == {"press_release"}
        assert "Apple" not in p["state"]["press_release"] and "2026" not in p["state"]["press_release"]
    assert set(themes["questions"]) == set(THEME_QUESTIONS)


def test_select_drops_non_earnings_and_duplicates():
    recs = [
        record("a", when="2026-01-08", is_earnings=0.2),   # pre-announcement, not a results release
        record("b", when="2026-01-25"),                    # kept although 17 days after "a"
        record("c", when="2026-02-02"),                    # second Item 2.02 within 20 days of "b"
        record("d", when="2026-04-28"),
        record("e", ticker="MSFT", when="2026-01-27"),
    ]
    keep, skipped = R.select(recs)
    assert [r["id"] for r in keep] == ["b", "e", "d"]
    assert skipped == {"a": "not_earnings", "c": "duplicate"}


def test_select_uses_published_releases_as_reference():
    keep, skipped = R.select([record("new", when="2026-08-05")], published=[record("old", when="2026-07-30")])
    assert keep == [] and skipped == {"new": "duplicate"}


def test_save_load_roundtrip_is_sorted_and_line_per_release(radar_dir):
    data = {"model": "m", "skipped": {"z": "duplicate"}, "releases": [record("b", when="2026-04-28"),
                                                                       record("a", when="2026-01-25")]}
    R.save(data)
    text = R.PATHS.radar_releases.read_text()
    assert len(text.splitlines()) == 4  # header, two releases, closing bracket
    back = R.load()
    assert [r["id"] for r in back["releases"]] == ["a", "b"] and back["skipped"] == {"z": "duplicate"}


def test_summarize_quarters_sectors_and_previous_guidance():
    releases = [
        record("a1", "AAPL", "2026-04-30", "reaffirmed"),
        record("a2", "AAPL", "2026-07-30", "raised"),
        record("m1", "MSFT", "2026-07-28", "lowered"),
        record("j1", "JPM", "2026-07-14", "none"),
        record("j2", "JPM", "2026-10-02", "none"),
    ]
    s = R.summarize(releases, today=date(2026, 10, 4))
    q = {x["quarter"]: x for x in s["quarters"]}
    assert q["2026Q3"]["n"] == 3 and not q["2026Q3"]["partial"] and q["2026Q4"]["partial"]
    assert q["2026Q3"]["guidance"]["raised"] == pytest.approx(1 / 3, abs=1e-4)
    assert q["2026Q3"]["guidance_net"] == 0.0
    assert q["2026Q3"]["flags"] == {"demand_weakness": 1.0, "margin_pressure": 1.0, "uncertainty": 1.0}
    assert q["2026Q3"]["themes"] == {k: None for k in THEME_QUESTIONS}  # never asked
    assert s["meta"]["has_themes"] is False and s["meta"]["releases"] == 5
    sectors = {x["sector"]: x for x in s["sectors"]}
    assert sectors["Information Technology"]["companies"] == 2 and sectors["Financials"]["n"] == 2
    apple = next(c for c in s["companies"] if c["ticker"] == "AAPL")
    assert apple["last_guidance"] == "raised" and apple["prev_guidance"] == "reaffirmed"
    assert [r["id"] for r in s["latest"]][:2] == ["j2", "a2"]
    assert s["latest"][0]["prev_guidance"] == "none" and s["latest"][-1]["prev_guidance"] is None
    json.dumps(s)  # everything is serializable


def test_summarize_theme_share_counts_only_releases_that_were_asked():
    releases = [
        record("a", "AAPL", "2026-07-30", themes={k: 0.9 for k in THEME_QUESTIONS}),
        record("b", "MSFT", "2026-07-28", themes={k: 0.1 for k in THEME_QUESTIONS}),
        record("c", "JPM", "2026-07-14"),
    ]
    q = R.summarize(releases, today=date(2026, 10, 4))["quarters"][0]
    assert q["themes"]["tariffs"] == 0.5


def test_update_scores_only_unknown_filings_and_appends(radar_dir, monkeypatch):
    R.save({"model": "m", "skipped": {"skip-1": "not_earnings"}, "releases": [record("old", "AAPL", "2026-04-30")]})
    seen = {}

    def fake_fetch(known, since, until):
        seen.update(known=known, since=since, until=until)
        return pd.DataFrame([
            filing("new-aapl", 320193, "2026-07-30 16:30"),
            filing("new-msft", 789019, "2026-07-28 16:05", text="Slides for the quarter."),
        ]), {"no-exhibit": "no_exhibit"}

    monkeypatch.setattr(R, "fetch_new_filings", fake_fetch)
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if set(body["questions"]) == set(THEME_QUESTIONS):
            return httpx.Response(200, json=theme_response(ai=0.8))
        slides = "Slides" in body["state"]["press_release"]
        return httpx.Response(200, json=core_response("lowered", is_earnings=0.1 if slides else 0.95))

    client = DecisionClient(cache=Cache(radar_dir / "c.sqlite"), transport=httpx.MockTransport(handler),
                            cap_usd=1.0, api_key="test")
    new = R.update(today=date(2026, 8, 1), client=client)
    assert seen["known"] == {"old", "skip-1"} and seen["until"] == date(2026, 8, 1)
    assert len(calls) == 4  # core + themes for each of the two new filings
    assert [r["id"] for r in new] == ["new-aapl"] and new[0]["themes"]["ai"] == 0.8
    data = R.load()
    assert [r["id"] for r in data["releases"]] == ["old", "new-aapl"]
    assert data["skipped"] == {"skip-1": "not_earnings", "no-exhibit": "no_exhibit", "new-msft": "not_earnings"}
