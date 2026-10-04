"""Every question sent to the decision model, in one place, so the design can be reviewed and frozen.

Questions are in English and written to be atomic and direct. Numbers are converted to words in
code before the model sees them, see ``describe_reaction``.

Changing anything in this file after the pre-registration lock changes its hash, and the
pipeline then refuses to score holdout events (see ``prereg.py``).
"""

from __future__ import annotations

import math

# =========================================================================== variant: text only
# State: {"press_release": <narrative text>}. The model never sees prices here.
TEXT_QUESTIONS: dict[str, dict] = {
    "is_earnings_release": {
        "type": "noul",
        "instructions": "Is `press_release` an announcement of a company's quarterly or annual financial results?",
    },
    "guidance": {
        "type": "choice",
        "instructions": "What does `press_release` say about the company's financial guidance for future periods?",
        "criteria": {
            "raised": "Guidance for at least one key metric is raised and none is lowered",
            "lowered": "Guidance for at least one key metric is lowered and none is raised",
            "mixed": "Some guidance is raised and some is lowered",
            "reaffirmed": "Previous guidance is reaffirmed or kept unchanged",
            "new_period": "Guidance is given for a new period without saying how it compares with previous guidance",
            "withdrawn": "Guidance is withdrawn or suspended",
            "none": "The release gives no financial guidance",
        },
    },
    "results_strength": {
        "type": "score",
        "instructions": "How strong are the financial results reported in `press_release`?",
        "criteria": [
            "Clearly weak: declines or shortfalls on the key metrics",
            "Somewhat weak",
            "Mixed or unremarkable",
            "Somewhat strong",
            "Clearly strong: broad growth or records on the key metrics",
        ],
    },
    "outlook_tone": {
        "type": "score",
        "instructions": "How does management describe the business outlook for the coming periods in `press_release`?",
        "criteria": ["Very negative", "Negative", "Neutral or no outlook given", "Positive", "Very positive"],
    },
    "uncertainty": {
        "type": "score",
        "instructions": "How much uncertainty or caution about the future does management express in `press_release`?",
        "criteria": ["None", "A little", "A moderate amount", "A lot"],
    },
    "one_time_items": {
        "type": "noul",
        "instructions": "Do the results in `press_release` include significant one-time charges, impairments, or write-downs?",
    },
    "restructuring": {
        "type": "noul",
        "instructions": "Does `press_release` announce restructuring, layoffs, or a cost-cutting program?",
    },
    "demand_weakness": {
        "type": "noul",
        "instructions": "Does `press_release` describe weakening customer demand, orders, or bookings?",
    },
    "margin_pressure": {
        "type": "noul",
        "instructions": "Does `press_release` describe declining or pressured profit margins?",
    },
    "exec_departure": {
        "type": "noul",
        "instructions": "Does `press_release` announce that the CEO or CFO is leaving?",
    },
    "capital_return": {
        "type": "noul",
        "instructions": "Does `press_release` announce a new or larger share buyback or dividend?",
    },
    "transitory_driver": {
        "type": "noul",
        "instructions": "Is the main news in `press_release` caused by temporary or one-time factors rather than lasting changes in the business?",
    },
    # Deliberately naive: asks for the market outcome directly. Kept as a reference point.
    "naive_reaction": {
        "type": "score",
        "instructions": "How will investors react to `press_release`?",
        "criteria": ["Very negatively", "Negatively", "Little reaction", "Positively", "Very positively"],
    },
}

# =========================================================================== variant: text + reaction
# State: {"press_release": <text>, "initial_market_reaction": <sentence from describe_reaction>}.
REACTION_QUESTIONS: dict[str, dict] = {
    # PRIMARY pre-registered question (see docs/PREREGISTRATION.md).
    "news_vs_reaction": {
        "type": "choice",
        "instructions": "Comparing the news in `press_release` with `initial_market_reaction`, is the news better or worse than the market reaction implies?",
        "criteria": {
            "better": "The news is better than the reaction implies: the reaction is too negative or not positive enough",
            "in_line": "The reaction is about right for the news",
            "worse": "The news is worse than the reaction implies: the reaction is too positive or not negative enough",
        },
    },
    "overreaction": {
        "type": "noul",
        "instructions": "Is the price move in `initial_market_reaction` bigger than the news in `press_release` justifies?",
        "criteria": {
            "true": "The move is bigger than the news warrants",
            "false": "The move is proportionate to the news, or smaller",
        },
    },
    "underappreciated_longterm": {
        "type": "noul",
        "instructions": "Does `press_release` contain news about the company's long-term prospects that `initial_market_reaction` does not reflect?",
    },
    "direction_consistent": {
        "type": "noul",
        "instructions": "Does the direction of `initial_market_reaction` match the tone of the news in `press_release`?",
    },
}

# =========================================================================== variant: memory probe
# State: identity + date + reaction, and NO press release. If these answers predict returns,
# the model is recalling outcomes from pretraining, not reading.
PROBE_QUESTIONS: dict[str, dict] = {
    "outperform_next_month": {
        "type": "noul",
        "instructions": "Did the stock of `company` do better than the S&P 500 during the month after `event`?",
    },
    "outperform_next_quarter": {
        "type": "noul",
        "instructions": "Did the stock of `company` do better than the S&P 500 during the three months after `event`?",
    },
}


# =========================================================================== numbers -> words
def _size_label(z: float) -> str:
    a = abs(z)
    if a < 0.5:
        return "essentially no reaction"
    if a < 1.5:
        return "a small move"
    if a < 3:
        return "a moderate move"
    if a < 5:
        return "a large move"
    return "an extreme move"


def describe_reaction(r0_abn: float, r0_z: float) -> str:
    """Sentence describing the day-0 abnormal return, in words rather than bare numbers.

    ``r0_z`` scales the move by the stock's own pre-event volatility, so a 4% move reads as large
    for a utility and small for a volatile tech stock.
    """
    pct = abs(r0_abn) * 100
    direction = "above" if r0_abn >= 0 else "below"
    size = _size_label(r0_z if not math.isnan(r0_z) else r0_abn / 0.015)
    if size == "essentially no reaction":
        sign = ""
    else:
        sign = " positive" if r0_abn > 0 else " negative"
        size = size.replace(" move", f"{sign} move")
    return (
        f"On the first full trading day after this release, the company's stock closed {pct:.1f}% "
        f"{direction} the broader stock market. Compared with this stock's normal daily ups and "
        f"downs, that is {size}."
    )


# Counterfactual reactions for the sensitivity check: same text, different reaction.
COUNTERFACTUAL_REACTIONS: dict[str, tuple[float, float]] = {
    "cf_strong_neg": (-0.08, -4.0),
    "cf_flat": (0.0, 0.0),
    "cf_strong_pos": (0.08, 4.0),
}


# =========================================================================== request builders
def text_request(text: str) -> tuple[dict, dict]:
    return {"press_release": text}, TEXT_QUESTIONS


def reaction_request(text: str, reaction_sentence: str) -> tuple[dict, dict]:
    return {"press_release": text, "initial_market_reaction": reaction_sentence}, REACTION_QUESTIONS


def probe_request(company: str, ticker: str, event_date: str, reaction_sentence: str) -> tuple[dict, dict]:
    state = {
        "company": f"{company} (ticker {ticker})",
        "event": f"the company's financial results release on {event_date}",
        "initial_market_reaction": reaction_sentence,
    }
    return state, PROBE_QUESTIONS


ALL_QUESTION_SETS = {"text": TEXT_QUESTIONS, "reaction": REACTION_QUESTIONS, "probe": PROBE_QUESTIONS}
