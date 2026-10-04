import json

import httpx
import pytest

from decisionsignal.client import BudgetExceeded, Cache, DecisionClient, estimate_tokens, payload, request_key
from decisionsignal.questions import REACTION_QUESTIONS
from decisionsignal.score import flatten_answer

ANSWER = {
    "model": "pplx-decider-v1-27b",
    "answers": {
        "news_vs_reaction": {"type": "choice", "choice": "better",
                             "probabilities": {"better": 0.6, "in_line": 0.3, "worse": 0.1}, "confidence": 0.5},
        "overreaction": {"type": "noul", "noul": 0.2},
    },
    "usage": {"input_tokens": 1000, "output_tokens": 10},
}

# The sample response in docs.perplexity.ai/docs/decisions/quickstart (2026-10), values as sent.
PPLX_DOCS_RESPONSE = {
    "model": "pplx-decider-v1-27b",
    "answers": {
        "defect": {"type": "noul", "noul": 0.9424522889347015},
        "sentiment": {
            "type": "choice", "choice": "mixed", "confidence": 0.9255246944002182,
            "probabilities": {"positive": 0.020649883775315993, "mixed": 0.9503497962668123,
                              "negative": 0.02900031995787183},
        },
        "severity": {
            "type": "score", "score": 1.7838686319784252, "confidence": 0.7838686319784252,
            "legend": {"0": "Cosmetic", "1": "Inconvenient", "2": "Product unusable"},
            "probabilities": {"0": 0.008423954913615923, "1": 0.199283458194343, "2": 0.7922925868920411},
        },
    },
    "usage": {"input_tokens": 367, "output_tokens": 3},
}


def _client(tmp_path, handler, cap=1.0):
    return DecisionClient(cache=Cache(tmp_path / "c.sqlite"), transport=httpx.MockTransport(handler),
                     cap_usd=cap, api_key="test")


def test_cache_prevents_second_call(tmp_path):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json=ANSWER)

    c = _client(tmp_path, handler)
    p = payload({"press_release": "x"}, REACTION_QUESTIONS)
    assert c.call(p)["model"] == "pplx-decider-v1-27b"
    c.call(p)
    assert len(calls) == 1
    assert calls[0]["model"] == "pplx-decider-v1-27b"
    # Perplexity answers 400 to any unknown top-level field.
    assert set(calls[0]) == {"model", "state", "questions"}


def test_calls_the_decisions_endpoint_with_a_bearer_key(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=ANSWER)

    _client(tmp_path, handler).call(payload({"s": 1}, REACTION_QUESTIONS))
    assert str(seen[0].url) == "https://api.perplexity.ai/v1/decisions"
    assert seen[0].headers["authorization"] == "Bearer test"


def test_spend_is_billed_at_the_documented_price(tmp_path):
    c = _client(tmp_path, lambda req: httpx.Response(200, json=ANSWER))
    c.call(payload({"s": 1}, REACTION_QUESTIONS))
    assert c.spend.usd == pytest.approx(1000 * 0.04 / 1e6)


def test_estimate_counts_the_state_once_per_question():
    # Billing observed on the real API: the text is charged again for every question asked.
    text = {"press_release": "word " * 2000}
    one = dict(list(REACTION_QUESTIONS.items())[:1])
    ratio = estimate_tokens(payload(text, REACTION_QUESTIONS)) / estimate_tokens(payload(text, one))
    assert ratio == pytest.approx(len(REACTION_QUESTIONS), rel=0.1)


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


@pytest.mark.parametrize("status", [400, 413])
def test_rejected_request_is_recorded_not_raised(tmp_path, status):
    c = _client(tmp_path, lambda req: httpx.Response(status, text="bad question"))
    p = payload({"s": 1}, {})
    assert c.call(p)["error"] == "unprocessable"
    assert c.cache.get(request_key(p)) is None


def test_bad_key_raises(tmp_path):
    c = _client(tmp_path, lambda req: httpx.Response(401, json={"error": {"message": "invalid key"}}))
    with pytest.raises(httpx.HTTPStatusError):
        c.call(payload({"s": 1}, {}))


def test_flatten_answer():
    rows = flatten_answer("acc", "react_anon", ANSWER)
    by_q = {r["question"]: r for r in rows}
    assert by_q["news_vs_reaction"]["p_better"] == 0.6
    assert by_q["overreaction"]["value"] == 0.2


def test_flatten_perplexity_documented_response():
    by_q = {r["question"]: r for r in flatten_answer("acc", "text_anon", PPLX_DOCS_RESPONSE)}
    assert by_q["defect"]["value"] == pytest.approx(0.9425, abs=1e-4)
    assert by_q["sentiment"]["choice"] == "mixed"
    assert by_q["sentiment"]["p_mixed"] == pytest.approx(0.9503, abs=1e-4)
    # Three levels (0..2): the expected level 1.78 is normalized to 0..1.
    assert by_q["severity"]["value"] == pytest.approx(1.7838686319784252 / 2)
    assert by_q["severity"]["model"] == "pplx-decider-v1-27b"
