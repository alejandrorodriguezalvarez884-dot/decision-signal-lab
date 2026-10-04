"""Build decision-model requests for each event and variant, call the API, and store answers in long form."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import questions as Q
from .anonymize import anonymize
from .client import DecisionClient, payload
from .config import in_raw_sample
from .prereg import assert_locked

# Variant name -> what the model sees.
#   text_raw / text_anon       press release only (raw or identity-masked)
#   react_raw / react_anon     press release + day-0 reaction sentence, secondary questions
#   facts_raw / facts_anon     same state, the primary question alone      <- facts_anon is PRIMARY
#   probe                      company, date and reaction, NO press release (memorization probe)
#   cf_*                       masked text + a counterfactual reaction, primary question (sensitivity check)
# The raw variants exist only to compare against the masked ones (memorization check), so they
# are sent for a fixed sample of events: see config.RAW_SAMPLE_FRACTION.
RAW_VARIANTS = ("text_raw", "react_raw", "facts_raw")
MAIN_VARIANTS = ("text_raw", "text_anon", "react_raw", "react_anon", "facts_raw", "facts_anon", "probe")
CF_VARIANTS = tuple(Q.COUNTERFACTUAL_REACTIONS)


def _texts_for(ev: pd.Series) -> tuple[str, str]:
    raw = ev["text"]
    anon = anonymize(raw, ev["sec_name"] or "", [ev["price_ticker"]])
    return raw, anon


def build_payloads(events: pd.DataFrame, variants: tuple[str, ...]) -> list[tuple[str, str, dict]]:
    """Return (accession, variant, payload) triples."""
    out = []
    for _, ev in events.iterrows():
        raw, anon = _texts_for(ev)
        sentence = Q.describe_reaction(ev["r0_abn"], ev["r0_z"])
        send_raw = in_raw_sample(ev["accessionNumber"])
        for v in variants:
            if v in RAW_VARIANTS and not send_raw:
                continue
            if v == "text_raw":
                state, qs = Q.text_request(raw)
            elif v == "text_anon":
                state, qs = Q.text_request(anon)
            elif v == "react_raw":
                state, qs = Q.reaction_request(raw, sentence)
            elif v == "react_anon":
                state, qs = Q.reaction_request(anon, sentence)
            elif v == "facts_raw":
                state, qs = Q.primary_request(raw, sentence)
            elif v == "facts_anon":
                state, qs = Q.primary_request(anon, sentence)
            elif v == "probe":
                state, qs = Q.probe_request(
                    ev["sec_name"], ev["price_ticker"], ev["event_date"].strftime("%B %d, %Y"), sentence
                )
            elif v in Q.COUNTERFACTUAL_REACTIONS:
                r, z = Q.COUNTERFACTUAL_REACTIONS[v]
                state, qs = Q.primary_request(anon, Q.describe_reaction(r, z))
            else:
                raise ValueError(v)
            out.append((ev["accessionNumber"], v, payload(state, qs)))
    return out


def flatten_answer(accession: str, variant: str, resp: dict) -> list[dict]:
    if "answers" not in resp:
        return [{"accessionNumber": accession, "variant": variant, "question": None,
                 "error": resp.get("error", "unknown")}]
    rows = []
    for qid, a in resp["answers"].items():
        row = {"accessionNumber": accession, "variant": variant, "question": qid,
               "qtype": a.get("type"), "model": resp.get("model"), "error": None}
        if a.get("type") == "noul":
            row["value"] = a["noul"]
        elif a.get("type") == "choice":
            row["choice"] = a["choice"]
            row["confidence"] = a.get("confidence")
            for opt, p in a["probabilities"].items():
                row[f"p_{opt}"] = p
        elif a.get("type") == "score":
            n = len(a["probabilities"])
            row["value"] = a["score"] / (n - 1) if n > 1 else np.nan  # normalized to 0..1
            row["confidence"] = a.get("confidence")
        rows.append(row)
    return rows


def score_events(events: pd.DataFrame, variants: tuple[str, ...], client: DecisionClient | None = None) -> pd.DataFrame:
    if (events["split"] == "holdout").any():
        assert_locked()
    client = client or DecisionClient()
    triples = build_payloads(events, variants)
    responses = client.call_many([p for _, _, p in triples], desc=f"Decider {'/'.join(variants)}")
    rows = []
    for (acc, v, _), resp in zip(triples, responses):
        rows.extend(flatten_answer(acc, v, resp))
    return pd.DataFrame(rows)


def counterfactual_sample(events: pd.DataFrame, n: int, seed: int = 7) -> pd.DataFrame:
    design = events[events["split"] == "design"]
    return design.sample(min(n, len(design)), random_state=seed)
