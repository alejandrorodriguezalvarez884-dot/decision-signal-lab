import json

import httpx
import pytest

from jevsignal.jev import BudgetExceeded, Cache, JevClient, payload
from jevsignal.questions import REACTION_QUESTIONS
from jevsignal.score import flatten_answer

ANSWER = {
    "model": "jev-1.13.0",
    "answers": {
        "news_vs_reaction": {"type": "choice", "choice": "better",
                             "probabilities": {"better": 0.6, "in_line": 0.3, "worse": 0.1}, "confidence": 0.5},
        "overreaction": {"type": "noul", "noul": 0.2},
    },
    "usage": {"input_tokens": 1000, "output_tokens": 10},
}


def _client(tmp_path, handler, cap=1.0):
    return JevClient(cache=Cache(tmp_path / "c.sqlite"), transport=httpx.MockTransport(handler),
                     cap_usd=cap, api_key="test")


def test_cache_prevents_second_call(tmp_path):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json=ANSWER)

    c = _client(tmp_path, handler)
    p = payload({"press_release": "x"}, REACTION_QUESTIONS)
    assert c.call(p)["model"] == "jev-1.13.0"
    c.call(p)
    assert len(calls) == 1
    assert calls[0]["model"] == "jev-1.13.0"  # pinned version, not the alias


def test_retries_on_429(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    seq = iter([httpx.Response(429, headers={"retry-after": "0"}), httpx.Response(200, json=ANSWER)])
    c = _client(tmp_path, lambda req: next(seq))
    assert "answers" in c.call(payload({"s": 1}, {}))


def test_budget_refuses_large_batch(tmp_path):
    c = _client(tmp_path, lambda req: httpx.Response(200, json=ANSWER), cap=0.000001)
    big = [payload({"press_release": "word " * 5000, "i": i}, REACTION_QUESTIONS) for i in range(3)]
    with pytest.raises(BudgetExceeded):
        c.call_many(big)


def test_422_is_recorded_not_raised(tmp_path):
    c = _client(tmp_path, lambda req: httpx.Response(422, text="bad question"))
    assert c.call(payload({"s": 1}, {}))["error"] == "unprocessable"


def test_flatten_answer():
    rows = flatten_answer("acc", "react_anon", ANSWER)
    by_q = {r["question"]: r for r in rows}
    assert by_q["news_vs_reaction"]["p_better"] == 0.6
    assert by_q["overreaction"]["value"] == 0.2
