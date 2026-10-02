"""Signals that do not use Jev. Jev only earns credit for what it adds beyond these.

Loughran-McDonald dictionary: free for academic research; commercial use needs a license from
the authors (relevant if this becomes a product; see docs/METHODOLOGY.md).
"""

from __future__ import annotations

import warnings
from functools import lru_cache

import pandas as pd

from .features import mismatch_signal


@lru_cache(maxsize=1)
def _lm():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        import pysentiment2 as ps
    return ps.LM()


def lm_tone(text: str) -> float:
    lm = _lm()
    return float(lm.get_score(lm.tokenize(text))["Polarity"])


def add_baselines(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    design = p["split"] == "design"
    p["base__lm_tone"] = p["text"].map(lm_tone)
    # Post-earnings drift: continuation in the direction of the day-0 reaction.
    p["base__continuation"] = p["r0_z"]
    # Short-term reversal of the day-0 move.
    p["base__reversal"] = -p["r0_z"]
    # Approach B without Jev: dictionary tone not explained by the reaction.
    p["base__lm_mismatch"] = mismatch_signal(p["base__lm_tone"], p["r0_z"], design)
    p["base__momentum"] = p["momentum"]
    return p
