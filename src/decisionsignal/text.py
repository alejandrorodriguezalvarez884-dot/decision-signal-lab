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

# Headings that open a boilerplate section; the section is skipped up to the next real heading.
# Legal and non-GAAP headings are matched anywhere in the line ("A Caution Concerning
# Forward-Looking Statements"). Conference-call headings only at the start, so a sub-headline
# such as "Company to Host Conference Call on December 3" does not swallow the lead paragraph.
_BOILERPLATE_HEAD = re.compile(
    r"forward[- ]looking|safe harbor|\bcaution(?:ary)?\b|private securities litigation reform act"
    r"|non[- ]gaap\b.*\b(?:measures?|information|reconciliations?|disclosures?)\b"
    r"|\b(?:use|uses|comments?|notes?|discussion|explanation) (?:of|on|regarding|about) non[- ]gaap"
    r"|^reconciliations? of\b"
    r"|^about [A-Z]"
    r"|^(?:conference call|webcast|earnings call)\b"
    r"|^(?:investor|media|press|public)(?: relations)? contacts?\b|^contacts?\s*:?$"
    r"|^for (?:more|further|additional) information\b|^source:"
    r"|^glossary\b|^definitions?\b",
    re.I,
)
# End of the narrative: the "###" that closes a press release, or the title of a primary
# financial statement. Statements come after the narrative, so everything from the first one on
# is tables, their captions and footnotes, and reconciliations.
_NARRATIVE_END = re.compile(
    r"^#(?:\s*#){2,}$"
    r"|^(?:(?:unaudited|condensed|consolidated|summary|selected)\s+)*"
    r"(?:statements? of (?:consolidated )?(?:operations|income|earnings|cash flows?"
    r"|comprehensive (?:income|loss)|financial (?:position|condition))"
    r"|(?:income|cash flow) statements?)\b"
    # "Balance sheet and liquidity" is a narrative heading; a statement title has a qualifier.
    r"|^(?:(?:unaudited|condensed|consolidated|summary|selected)\s+)+balance sheets?\b"
    r"|^(?:financial |reconciliation )?(?:tables|statements|schedules) (?:to )?follow\b"
    r"|^note to editors\b",
    re.I,
)
# Lines that never carry narrative: page furniture, table captions, EDGAR document headers.
_NOISE_LINE = re.compile(
    r"^(?:page\s+)?\d{1,3}(?:\s+of\s+\d{1,3})?$"
    r"|^-+\s*more\s*-+$|^[_\-=]{5,}$"
    r"|^\(?\s*unaudited\s*\)?$"
    r"|^\(?\s*(?:dollars |amounts |\$ ?)?in (?:thousands|millions|billions)\b[^.]{0,80}$"
    r"|^\S+\.html?$|^ex(?:hibit)?[- ]?99(?:\.\d+)?(?:\s+\d+)?$"
    r"|^(?:©|\(c\)|copyright\b)",
    re.I,
)
# A table footnote: "(1) ...", "1 Includes ...", "a The Company's ...", "* ...", "Note: ...".
_FOOTNOTE = re.compile(r"^(?:\(\w{1,2}\)|\d{1,2}\)|\d{1,2}\.?\s?(?=[A-Z])|[a-z] (?=[A-Z\x22“])|[*†‡]|notes?:|n/m\b)", re.I)
_COMPANY_SUFFIX = re.compile(r"\b(?:inc|corp|ltd|plc|co|llc|n\.v|s\.a)\.$", re.I)
_CONTACT_LINE = re.compile(r"\S+@\S+\.\w{2,}")
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


def _is_bare_title(p: str) -> bool:
    if len(p) > 60 or len(p.split()) > 8 or not p[0].isalnum():
        return False
    return _looks_like_heading(p) or bool(_COMPANY_SUFFIX.search(p))


def _page_furniture(paras: list[str]) -> set[str]:
    """Short lines printed three or more times: running headers and footers of a paginated
    release. Their first appearance may be the headline, so they are not dropped here."""
    counts: dict[str, int] = {}
    for p in paras:
        if len(p) < 80:
            counts[p.lower()] = counts.get(p.lower(), 0) + 1
    return {p for p, n in counts.items() if n >= 3}


def clean_paragraphs(paras: list[str]) -> list[str]:
    out: list[str] = []
    skipping = False
    furniture = _page_furniture(paras)
    for p in paras:
        if len(p) < 3 or _NOISE_LINE.match(p):
            continue
        heading = _looks_like_heading(p)
        if heading and _NARRATIVE_END.search(p):
            break
        if heading and _BOILERPLATE_HEAD.search(p):
            skipping = True
            continue
        if skipping and heading and len(p) > 3 and _digit_ratio(p) < 0.2 and p.lower() not in furniture:
            skipping = False  # a new, non-boilerplate section starts
        if skipping:
            continue
        if _LEGAL_PARAGRAPH.search(p) and len(p) > 300:
            continue
        if _digit_ratio(p) > 0.35:
            continue
        if len(p) < 200 and _CONTACT_LINE.search(p):
            continue
        out.append(p)
    # Drop repeats (running headers on every page of a PDF-to-HTML conversion), ignoring case.
    seen: set[str] = set()
    out = [p for p in out if not (p.lower() in seen or seen.add(p.lower()))]
    # What trails the last real paragraph is what tables leave behind when they are removed:
    # their titles and footnotes. Bullets are left alone: a release can end on its highlights.
    while out and (_is_bare_title(out[-1]) or _FOOTNOTE.match(out[-1])):
        out.pop()
    return out


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
