"""Turn Jev's long-form answers into one row of numeric signals per event.

Sign convention for every *signal*: higher value = expect HIGHER forward abnormal return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Guidance option -> direction. Expected value under Jev's probabilities.
GUIDANCE_DIRECTION = {
    "raised": 1.0,
    "lowered": -1.0,
    "withdrawn": -1.0,
    "mixed": 0.0,
    "reaffirmed": 0.0,
    "new_period": 0.0,
    "none": 0.0,
}

# Pre-specified (NOT fitted) text-only composite for approach B. Weights are +-1 by economic
# direction, applied to features standardized on the design split. Fitted composites are
# reported separately as exploratory.
TEXT_COMPOSITE_SIGNS = {
    "results_strength": 1,
    "outlook_tone": 1,
    "guidance_dir": 1,
    "uncertainty": -1,
    "demand_weakness": -1,
    "margin_pressure": -1,
}

PRIMARY_SIGNAL = "react_anon__nvr"  # P(better) - P(worse), masked text + reaction
PRIMARY_TARGET = "fwd_abn_20"


def wide_features(answers: pd.DataFrame) -> pd.DataFrame:
    ok = answers[answers["error"].isna() & answers["question"].notna()].copy()
    rows: dict[str, dict] = {}
    for rec in ok.to_dict("records"):
        r = rows.setdefault(rec["accessionNumber"], {"accessionNumber": rec["accessionNumber"]})
        prefix = f"{rec['variant']}__{rec['question']}"
        if rec["qtype"] in ("noul", "score"):
            r[prefix] = rec["value"]
        if rec["qtype"] == "score":
            r[prefix + "__conf"] = rec.get("confidence")
        if rec["qtype"] == "choice":
            for k, v in rec.items():
                if k.startswith("p_") and pd.notna(v):
                    r[f"{prefix}__{k}"] = v
            r[prefix + "__conf"] = rec.get("confidence")
    wide = pd.DataFrame(list(rows.values()))
    return add_derived(wide)


def add_derived(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    for v in ("react_raw", "react_anon", "cf_strong_neg", "cf_flat", "cf_strong_pos"):
        b, wo = f"{v}__news_vs_reaction__p_better", f"{v}__news_vs_reaction__p_worse"
        if b in w and wo in w:
            w[f"{v}__nvr"] = w[b] - w[wo]
    for v in ("text_raw", "text_anon"):
        cols = [f"{v}__guidance__p_{k}" for k in GUIDANCE_DIRECTION]
        if all(c in w for c in cols):
            w[f"{v}__guidance_dir"] = sum(w[f"{v}__guidance__p_{k}"] * d for k, d in GUIDANCE_DIRECTION.items())
    return w


def event_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Signals that combine Jev answers with event data (reaction). Panel = events + features."""
    p = panel.copy()
    design = p["split"] == "design"
    for v in ("react_raw", "react_anon"):
        col = f"{v}__overreaction"
        if col in p:
            # Overreaction expected -> bet against the day-0 direction.
            p[f"{v}__reversal_signal"] = -np.sign(p["r0_abn"]) * (p[col] - 0.5)
    for v in ("text_raw", "text_anon"):
        if all(f"{v}__{f}" in p for f in TEXT_COMPOSITE_SIGNS):
            p[f"{v}__composite"] = text_composite(p, v, design)
            p[f"{v}__mismatch"] = mismatch_signal(p[f"{v}__composite"], p["r0_z"], design)
        if f"{v}__naive_reaction" in p:
            p[f"{v}__naive_mismatch"] = mismatch_signal(p[f"{v}__naive_reaction"], p["r0_z"], design)
    return p


def text_composite(df: pd.DataFrame, variant: str, design_mask: pd.Series) -> pd.Series:
    """Equal-weight signed composite of standardized text features (no fitting to returns)."""
    total = pd.Series(0.0, index=df.index)
    for feat, sign in TEXT_COMPOSITE_SIGNS.items():
        col = f"{variant}__{feat}"
        x = df[col]
        mu, sd = x[design_mask].mean(), x[design_mask].std()
        total = total + sign * (x - mu) / (sd if sd and sd > 0 else 1.0)
    return total / len(TEXT_COMPOSITE_SIGNS)


def mismatch_signal(text_signal: pd.Series, r0_z: pd.Series, design_mask: pd.Series) -> pd.Series:
    """Approach B: the part of the text's tone NOT explained by the day-0 reaction.

    Residual of a design-split OLS of the text signal on the reaction (z-scaled). Positive means
    the text reads better than the price move suggests, i.e. expect upward drift.
    """
    m = design_mask & text_signal.notna() & r0_z.notna()
    x, y = r0_z[m].clip(-10, 10), text_signal[m]
    if len(x) < 10:
        return pd.Series(np.nan, index=text_signal.index)
    beta, alpha = np.polyfit(x, y, 1)
    return text_signal - (alpha + beta * r0_z.clip(-10, 10))
