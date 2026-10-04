"""Find 8-K Item 2.02 (Results of Operations) filings and download their EX-99 press release.

Timing source of truth: the "Accepted" timestamp on the filing index page, which EDGAR prints in
US Eastern time. The submissions JSON also carries ``acceptanceDateTime``, but its "Z" suffix is
unreliable, so it is only kept for cross-checking. Using EDGAR acceptance is conservative: the
same press release usually crosses the newswire minutes *earlier*, never later.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

from .config import PATHS, SEC_MAX_RPS, sec_user_agent
from .http import RateLimiter, cached_get

SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/"
NY = "America/New_York"

_limiter = RateLimiter(SEC_MAX_RPS)
_client: httpx.Client | None = None


def _get(url: str) -> bytes:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=60, follow_redirects=True)
    return cached_get(
        url, headers={"User-Agent": sec_user_agent()}, limiter=_limiter, client=_client
    )


def _recent_frame(block: dict) -> pd.DataFrame:
    cols = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "items", "primaryDocument"]
    return pd.DataFrame({c: block.get(c, []) for c in cols})


def list_item_202_filings(cik: int, start: date, end: date) -> pd.DataFrame:
    """All original 8-Ks (no amendments) for ``cik`` that report Item 2.02 within the window."""
    sub = json.loads(_get(SUBMISSIONS_URL.format(name=f"CIK{cik:010d}.json")))
    frames = [_recent_frame(sub["filings"]["recent"])]
    for extra in sub["filings"].get("files", []):
        if extra.get("filingTo", "9999") >= start.isoformat():
            frames.append(_recent_frame(json.loads(_get(SUBMISSIONS_URL.format(name=extra["name"])))))
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["form"] == "8-K") & df["items"].fillna("").str.contains(r"\b2\.02\b")]
    df = df[(df["filingDate"] >= start.isoformat()) & (df["filingDate"] <= end.isoformat())]
    df = df.assign(cik=cik, sic=sub.get("sic"), sec_name=sub.get("name"))
    return df.drop_duplicates("accessionNumber").reset_index(drop=True)


@dataclass
class FilingDocs:
    accepted_et: pd.Timestamp
    exhibit_url: str | None
    exhibit_type: str | None


_ACCEPTED_RE = re.compile(r"Accepted</div>\s*<div class=\"info\">([0-9:\- ]+)</div>", re.S)


def parse_index_page(html: str) -> FilingDocs:
    m = _ACCEPTED_RE.search(html)
    if not m:
        raise ValueError("no Accepted timestamp on index page")
    accepted = pd.Timestamp(m.group(1).strip()).tz_localize(NY)
    soup = BeautifulSoup(html, "lxml")
    best: tuple[int, str, str] | None = None
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        doc_type = cells[3].get_text(strip=True).upper()
        link = cells[2].find("a")
        if not link or not doc_type.startswith("EX-99"):
            continue
        href = link["href"]
        if not href.lower().endswith((".htm", ".html", ".txt")):
            continue
        # Prefer EX-99.1 (the press release by convention), then any other EX-99.x.
        rank = 0 if doc_type in ("EX-99.1", "EX-99.01", "EX-99") else 1
        if best is None or rank < best[0]:
            url = href if href.startswith("http") else "https://www.sec.gov" + href.split("?")[0]
            if "/ix?doc=" in href:
                url = "https://www.sec.gov" + href.split("/ix?doc=")[1]
            best = (rank, url, doc_type)
    return FilingDocs(accepted, best[1] if best else None, best[2] if best else None)


def fetch_filing_docs(cik: int, accession: str) -> FilingDocs:
    acc_nodash = accession.replace("-", "")
    base = ARCHIVE.format(cik=cik, acc_nodash=acc_nodash)
    html = _get(base + f"{accession}-index.htm").decode("utf-8", errors="replace")
    return parse_index_page(html)


def fetch_exhibit_html(url: str) -> str:
    return _get(url).decode("utf-8", errors="replace")


def collect_filings(universe: pd.DataFrame, start: date, end: date, limit_ciks: int | None = None) -> pd.DataFrame:
    """Build the filing table: one row per 8-K Item 2.02 with acceptance time and exhibit URL.

    Only filings made while the company was an S&P 500 member are kept (point-in-time universe).
    """
    ciks = universe["cik"].dropna().astype(int).unique().tolist()
    if limit_ciks:
        ciks = ciks[:limit_ciks]
    rows = []
    for cik in tqdm(ciks, desc="EDGAR submissions"):
        try:
            rows.append(list_item_202_filings(cik, start, end))
        except httpx.HTTPStatusError as exc:
            print(f"skip CIK {cik}: {exc.response.status_code}")
    filings = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if filings.empty:
        return filings

    out = []
    for rec in tqdm(filings.to_dict("records"), desc="EDGAR filing indexes"):
        try:
            docs = fetch_filing_docs(rec["cik"], rec["accessionNumber"])
        except (httpx.HTTPStatusError, ValueError) as exc:
            print(f"skip {rec['accessionNumber']}: {exc}")
            continue
        rec.update(
            accepted_et=docs.accepted_et,
            exhibit_url=docs.exhibit_url,
            exhibit_type=docs.exhibit_type,
        )
        out.append(rec)
    df = pd.DataFrame(out)
    df = _attach_membership(df, universe)
    df.to_parquet(PATHS.filings, index=False)
    return df


def _attach_membership(df: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    uni = universe.dropna(subset=["cik"]).copy()
    uni["cik"] = uni["cik"].astype(int)
    uni["end_date"] = uni["end_date"].fillna(pd.Timestamp.max.normalize())
    merged = df.merge(uni[["cik", "start_date", "end_date", "price_ticker"]], on="cik", how="left")
    day = merged["accepted_et"].dt.tz_localize(None).dt.normalize()
    merged = merged[(merged["start_date"] <= day) & (merged["end_date"] >= day)]
    return merged.drop(columns=["start_date", "end_date"]).drop_duplicates("accessionNumber")
