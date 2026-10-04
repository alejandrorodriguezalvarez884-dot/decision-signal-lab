from decisionsignal.anonymize import anonymize, name_variants
from decisionsignal.edgar import parse_index_page
from decisionsignal.questions import describe_reaction
from decisionsignal.text import looks_like_earnings_release, narrative_text

RELEASE = """
<html><body>
<p><b>Acme Corp. Reports Third Quarter 2024 Results</b></p>
<p>SPRINGFIELD, Oct. 30, 2024 -- Acme Corp. (NYSE: ACME) today reported revenue growth of 12%
and raised its full-year outlook. "Demand remained strong," said the CEO.</p>
<table><tr><td>Revenue</td><td>$1,234</td><td>$1,100</td></tr>
<tr><td>Net income</td><td>$234</td><td>$200</td></tr></table>
<table><tr><td>Record bookings across every segment and region this quarter.</td></tr></table>
<p>Forward-Looking Statements</p>
<p>This press release contains forward-looking statements that involve risks and uncertainties.</p>
<p>About Acme Corp.</p>
<p>Acme makes anvils.</p>
</body></html>
"""


def test_narrative_keeps_prose_drops_tables_and_boilerplate():
    t = narrative_text(RELEASE)
    assert "raised its full-year outlook" in t
    assert "Record bookings" in t  # prose-only layout table kept
    assert "$1,234" not in t  # financial table dropped
    assert "forward-looking" not in t.lower()
    assert "anvils" not in t
    assert looks_like_earnings_release(t)


def test_anonymize_masks_identity_and_dates():
    t = narrative_text(RELEASE)
    a = anonymize(t, "ACME CORP", ["ACME"])
    assert "Acme" not in a and "ACME" not in a
    assert "2024" not in a
    assert "Oct. 30" not in a
    assert "the Company" in a and "[TICKER]" in a
    assert "revenue growth of 12%" in a  # content survives


def test_short_tickers_only_masked_with_exchange_prefix():
    out = anonymize("A strong quarter for AT&T (NYSE: T). We turned on T", "AT&T INC.", ["T"])
    assert out.startswith("A strong quarter")
    assert "[TICKER]" in out and "NYSE" not in out


def test_ticker_masking_is_case_sensitive():
    assert anonymize("NVDA rose; nvda is a word here", "NVIDIA CORP", ["NVDA"]) == \
        "[TICKER] rose; nvda is a word here"


def test_name_variants():
    assert "APPLE" in name_variants("APPLE INC.")
    assert "Walt Disney" in name_variants("The Walt Disney Company")


def test_describe_reaction():
    s = describe_reaction(-0.071, -3.2)
    assert "7.1% below" in s and "a large negative move" in s
    assert "essentially no reaction" in describe_reaction(0.002, 0.2)


INDEX = """
<div class="infoHead">Accepted</div>
<div class="info">2024-10-31 16:30:59</div>
<table class="tableFile" summary="Document Format Files">
<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>1</td><td>8-K</td><td><a href="/ix?doc=/Archives/edgar/data/1/000/a8k.htm">a8k.htm</a></td><td>8-K</td><td>1</td></tr>
<tr><td>2</td><td></td><td><a href="/Archives/edgar/data/1/000/ex992.htm">ex992.htm</a></td><td>EX-99.2</td><td>1</td></tr>
<tr><td>3</td><td></td><td><a href="/Archives/edgar/data/1/000/ex991.htm">ex991.htm</a></td><td>EX-99.1</td><td>1</td></tr>
</table>
"""


def test_parse_index_page_prefers_ex991_and_reads_eastern_time():
    docs = parse_index_page(INDEX)
    assert docs.exhibit_url.endswith("ex991.htm")
    assert docs.exhibit_type == "EX-99.1"
    assert str(docs.accepted_et.tz) == "America/New_York"
    assert docs.accepted_et.hour == 16 and docs.accepted_et.minute == 30


def _html(*paragraphs: str) -> str:
    return "<html><body>" + "".join(f"<p>{p}</p>" for p in paragraphs) + "</body></html>"


LEAD = ("SPRINGFIELD, Oct. 30, 2024 -- Acme Corp. today reported record third-quarter revenue of "
        "$14.3 billion and raised its full-year earnings outlook on strong demand.")
LEGAL = ("Certain statements in this release are forward-looking statements that involve risks and "
         "uncertainties, including demand, pricing, competition and the economy. " * 3)
NON_GAAP = ("Management uses these non-GAAP financial measures to evaluate the Company's current "
            "operating performance and to allow for period-to-period comparisons. " * 2)


def test_paginated_release_stops_at_the_financial_statements():
    # Layout of a PDF-style release: running header and page number on every page, legal
    # section with a long title, then statements whose tables are gone but whose captions,
    # footnotes and non-GAAP explanations are not.
    header = "Acme Corp. Reports Third-Quarter 2024 Financial Results"
    t = narrative_text(_html(
        "EX-99.1", "acme-ex991.htm", "Exhibit 99.1",
        "ACME CORP. REPORTS THIRD-QUARTER 2024 FINANCIAL RESULTS", LEAD,
        "Balance sheet and liquidity",
        "Acme reduced total debt by $680 million in the quarter and ended it with $11.7 billion of liquidity.",
        header, "Page 2",
        "Conference call and webcast details",
        "The company will conduct a live audio webcast of its conference call at 7:30 a.m. CT today.",
        "Guidance",
        "Acme expects full-year adjusted earnings per share between $0.70 and $1.30.",
        header, "Page 3",
        "Cautionary statement regarding forward-looking statements and information", LEGAL,
        header, "Page 4",
        "Acme Corp.", "Condensed Consolidated Statements of Operations",
        "(In millions, except share and per share amounts)", "(Unaudited)",
        "Note: Percent change may not recalculate due to rounding.",
        "(1)Not meaningful or greater than 100% change.",
        "Reconciliation of GAAP Financial Information to Non-GAAP Financial Information", NON_GAAP,
    ))
    assert t.splitlines()[0] == "ACME CORP. REPORTS THIRD-QUARTER 2024 FINANCIAL RESULTS"
    assert "ended it with $11.7 billion of liquidity" in t  # "Balance sheet ..." is narrative
    assert t.endswith("between $0.70 and $1.30.")
    for gone in ("EX-99.1", ".htm", "Page", "webcast", "forward-looking", "Unaudited", "In millions",
                 "Not meaningful", "non-GAAP"):
        assert gone not in t, gone
    assert t.count("Financial Results") + t.count("FINANCIAL RESULTS") == 1  # running header


def test_subheadline_mentioning_the_conference_call_keeps_the_lead():
    t = narrative_text(_html(
        "Acme Reports Third Quarter 2024 Results",
        "Company to Host Conference Call on December 3, 2024", LEAD,
        "Third Quarter Financial Highlights",
        "•Revenue of $14.3 billion, up 12 percent",
        "•Operating margin of 15.1 percent",
    ))
    assert "raised its full-year earnings outlook" in t
    assert t.endswith("•Operating margin of 15.1 percent")  # a release may end on its bullets


def test_back_matter_is_dropped():
    t = narrative_text(_html(
        "Acme Reports Third Quarter 2024 Results", LEAD,
        "Non-GAAP Financial Information", NON_GAAP,
        "A Caution Concerning Forward-Looking Statements", LEGAL,
        "Outlook",
        "For the fourth quarter, Acme forecasts revenue of $2.35 billion, plus or minus $100 million.",
        "Glossary of Terms",
        "Recurring Revenue: Consists of the revenue for the period from subscription plans.",
        "Spend: The sum of cost of revenue and operating expenses.",
        "Press Contact:", "Jane Doe", "Acme", "jane.doe@acme.example", "(555) 010-0000",
        "© 2024 Acme Corp. All rights reserved. Acme and the Acme logo are trademarks of Acme.",
        "# # #",
        "ACME CORP.", "Summary of Revenues", "(1) Totals may not sum due to rounding.",
    ))
    assert t.endswith("plus or minus $100 million.")
    assert "Outlook" in t  # a real section after the legal one is kept
    for gone in ("non-GAAP", "forward-looking", "Recurring Revenue", "Jane Doe", "©", "#",
                 "Summary of Revenues", "Totals may not sum"):
        assert gone not in t, gone
