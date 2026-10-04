"""Turn an EX-99 press-release HTML into the narrative text the model reads.

The model is asked about language, not arithmetic, and irrelevant context only adds noise and
cost, so the cleaner keeps the narrative (headline, highlights, management commentary,
outlook) and drops financial tables and legal boilerplate. Numbers inside sentences are kept:
"revenue grew 12%" is language, a 40-row income statement is not.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

NARRATIVE_MAX_CHARS = 24_000  # ~7k tokens; state budget is 32k tokens

_BOILERPLATE_HEAD = re.compile(
    r"^\s*(?:"
    r"forward[- ]looking statements?|safe harbor|cautionary (?:note|statement|language)s?"
    r"|(?:use of |about |reconciliation of |discussion of )?non[- ]gaap(?: financial)? (?:measures?|information)"
    r"|about [A-Z][\w&.,' -]{1,60}|conference call(?: and webcast)?(?: information)?|webcast(?: information)?"
    r"|investor (?:relations )?contacts?|media contacts?|contacts?:?|source:.*"
    r"|(?:condensed )?consolidated (?:statements?|balance sheets?)\b.*"
    r")\s*:?\s*$",
    re.I,
)
_LEGAL_PARAGRAPH = re.compile(
    r"forward[- ]looking statements?.{0,400}(?:risks?|uncertaint)", re.I | re.S
)


def _digit_ratio(s: str) -> float:
    chars = [c for c in s if not c.isspace()]
    if not chars:
        return 0.0
    return sum(c.isdigit() or c in "$%(),.-" for c in chars) / len(chars)


def html_to_paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        # Financial tables are mostly digits; layout tables holding prose are kept as text.
        if _digit_ratio(text) > 0.25 or len(table.find_all("tr")) > 15:
            table.decompose()
        else:
            table.replace_with(soup.new_string("\n" + text + "\n"))
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "tr"]):
        block.insert_after("\n")
    raw = soup.get_text()
    raw = raw.replace("\xa0", " ").replace("​", "")
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", raw)]
    return [p for p in paras if p]


def _looks_like_heading(p: str) -> bool:
    return len(p) < 120 and not p.rstrip().endswith((".", ";", ",")) and len(p.split()) <= 14


def clean_paragraphs(paras: list[str]) -> list[str]:
    out: list[str] = []
    skipping = False
    for p in paras:
        if _looks_like_heading(p) and _BOILERPLATE_HEAD.match(p):
            skipping = True
            continue
        if skipping and _looks_like_heading(p) and len(p) > 3 and _digit_ratio(p) < 0.2:
            skipping = False  # a new, non-boilerplate section starts
        if skipping:
            continue
        if _LEGAL_PARAGRAPH.search(p) and len(p) > 300:
            continue
        if _digit_ratio(p) > 0.35:
            continue
        if len(p) < 3:
            continue
        out.append(p)
    # Drop exact duplicates (headers repeated on every page of a PDF-to-HTML conversion).
    seen: set[str] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def narrative_text(html: str, max_chars: int = NARRATIVE_MAX_CHARS) -> str:
    text = "\n".join(clean_paragraphs(html_to_paragraphs(html)))
    if len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars)
        text = text[: cut if cut > max_chars * 0.8 else max_chars]
    return text


_EARNINGS_HINTS = re.compile(
    r"\b(?:quarter|fiscal|full[- ]year|annual)\b.{0,200}\b(?:results|earnings|revenue|net (?:income|sales)|EPS)\b",
    re.I | re.S,
)


def looks_like_earnings_release(text: str) -> bool:
    return bool(_EARNINGS_HINTS.search(text[:4000]))
