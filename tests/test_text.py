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
