"""Mask identity and calendar cues so Jev cannot look up what happened next from memory.

Jev is built on a pretrained language model with an undisclosed knowledge cutoff, so for older
events it may "remember" the stock's subsequent path. If the raw text predicts returns much better
than the masked text in the older period, memorization (not reading) is the likely source.

Masked: company name variants, ticker, years, explicit dates, fiscal-period labels.
Not masked (documented limitation): product names, executive names, distinctive facts.
"""

from __future__ import annotations

import re

_SUFFIXES = re.compile(
    r"[,.]?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|"
    r"n\.?v|s\.?a|ag|se|lp|llc|trust|bancorp|the)\.?$",
    re.I,
)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_DATE_PATTERNS = [
    re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19|20)\d\d\b", re.I),
    re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTHS})\.?,?\s+(?:19|20)\d\d\b", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}/(?:19|20)?\d\d\b"),
    re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b", re.I),
]
_YEAR = re.compile(r"\b(?:FY|F|Q[1-4]\s*)?'?(?:19|20)\d\d\b|\bFY\s*'?\d\d\b", re.I)


def name_variants(sec_name: str) -> list[str]:
    """'APPLE INC.' -> ['APPLE INC.', 'APPLE'] (matched case-insensitively)."""
    base = sec_name.strip()
    variants = {base}
    stripped = base
    for _ in range(3):
        new = _SUFFIXES.sub("", stripped).strip(" ,.")
        if new == stripped:
            break
        stripped = new
        variants.add(stripped)
    stripped = re.sub(r"^the\s+", "", stripped, flags=re.I)
    variants.add(stripped)
    # Remove short generic leftovers that would mask ordinary words.
    return sorted((v for v in variants if len(v) >= 3), key=len, reverse=True)


def anonymize(text: str, sec_name: str, tickers: list[str]) -> str:
    out = text
    for t in {t.upper() for t in tickers if t}:
        variants = {t, t.replace("-", "."), t.replace("-", "")}
        for v in variants:
            # Tickers are matched case-sensitively ('ON' must not mask 'on'). Short tickers such as
            # 'A', 'T' or 'GE' are only masked after an exchange prefix, or 'A strong quarter' breaks.
            prefix = r"(?:NYSE|NASDAQ|Nasdaq)\s?:\s?" if len(v) <= 2 else r"(?:(?:NYSE|NASDAQ|Nasdaq)\s?:\s?)?"
            out = re.sub(rf"(?<![\w.]){prefix}{re.escape(v)}(?![\w])", "[TICKER]", out)
    # Names after tickers, so a name equal to the ticker ('ACME') is still tagged as a ticker.
    for v in name_variants(sec_name):
        out = re.sub(rf"\b{re.escape(v)}(?:'s|’s)?\b", "the Company", out, flags=re.I)
    for pat in _DATE_PATTERNS:
        out = pat.sub("[DATE]", out)
    out = _YEAR.sub("[YEAR]", out)
    return out
