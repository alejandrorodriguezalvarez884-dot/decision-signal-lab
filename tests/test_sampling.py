import httpx
import pandas as pd
import pytest

from decisionsignal import config
from decisionsignal.client import BudgetExceeded, Cache, DecisionClient, payload
from decisionsignal.questions import REACTION_QUESTIONS
from decisionsignal.score import MAIN_VARIANTS, RAW_VARIANTS, build_payloads

ANSWER = {"model": "pplx-decider-v1-27b", "answers": {}, "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}


def _events(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "accessionNumber": [f"0000000000-24-{i:06d}" for i in range(n)],
        "text": "Acme Corp. reported record revenue.", "sec_name": "ACME CORP", "price_ticker": "ACME",
        "r0_abn": 0.02, "r0_z": 1.0, "event_date": pd.Timestamp("2024-10-30"),
    })


def test_sample_membership_is_stable_and_close_to_the_fraction():
    keys = [f"k{i}" for i in range(5000)]
    picked = [k for k in keys if config.in_sample("raw", k, 0.15)]
    assert picked == [k for k in keys if config.in_sample("raw", k, 0.15)]
    assert 0.13 < len(picked) / len(keys) < 0.17
    assert set(picked) <= {k for k in keys if config.in_sample("raw", k, 0.5)}  # samples nest
    assert set(picked) != {k for k in keys if config.in_sample("company", k, 0.15)}


def test_raw_variants_only_go_out_for_the_raw_sample():
    ev = _events(400)
    triples = build_payloads(ev, MAIN_VARIANTS)
    by_variant = pd.DataFrame(triples, columns=["acc", "variant", "payload"]).groupby("variant")["acc"].apply(set)
    in_raw = {a for a in ev["accessionNumber"] if config.in_raw_sample(a)}
    assert 0 < len(in_raw) < len(ev)
    for v in RAW_VARIANTS:
        assert by_variant[v] == in_raw
    for v in ("text_anon", "react_anon", "probe"):
        assert by_variant[v] == set(ev["accessionNumber"])


def test_total_budget_counts_what_earlier_runs_already_paid(tmp_path):
    def client(total):
        return DecisionClient(cache=Cache(tmp_path / "c.sqlite"), cap_usd=1.0, api_key="test", total_cap_usd=total,
                              transport=httpx.MockTransport(lambda req: httpx.Response(200, json=ANSWER)))

    client(10.0).call(payload({"s": 1}, REACTION_QUESTIONS))  # pays 1M tokens = $0.04
    later = client(0.05)
    assert later.spend.prior_usd == pytest.approx(0.04)
    big = [payload({"press_release": "word " * 20000, "i": i}, REACTION_QUESTIONS) for i in range(3)]
    with pytest.raises(BudgetExceeded, match="DECIDER_TOTAL_MAX_USD"):
        later.call_many(big)
    with pytest.raises(BudgetExceeded, match="DECIDER_TOTAL_MAX_USD"):
        later.call(payload({"s": 2}, REACTION_QUESTIONS))  # this one answer would cross the ceiling


def test_universe_is_the_fixed_sp100_list_under_any_ticker():
    from decisionsignal.universe import restrict_to_sp100

    assert len(config.SP100_DEC_2020) == 101 and len(set(config.SP100_DEC_2020)) == 101
    spells = pd.DataFrame({"ticker": ["FB", "META", "BRK.B", "AAPL", "AAL", "ABNB"]})
    assert restrict_to_sp100(spells)["ticker"].tolist() == ["FB", "META", "BRK.B", "AAPL"]
