import pytest

from app.ingest.normalize import (
    MIN_QUOTE_WORDS,
    VerifyResult,
    normalize,
    token_f1,
    verify_quote,
)

SENTENCE = "This Agreement shall be governed by the laws of Delaware."


def test_normalize_collapses_whitespace_and_case():
    assert normalize("This  Agreement\n\tIS") == "this agreement is"


def test_normalize_maps_quotes_and_dashes():
    assert normalize("“Term” – ‘x’") == "\"term\" - 'x'"


def test_normalize_removes_soft_hyphen():
    assert normalize("compe­tition") == "competition"


def test_normalize_joins_line_break_hyphenation():
    assert normalize("compe-\ntition") == "competition"
    assert normalize("well-known") == "well-known"


def test_verify_finds_quote_on_its_page():
    pages = ["intro text", SENTENCE]
    result = verify_quote("this  agreement SHALL be governed\nby the laws of Delaware.", pages)
    assert result == VerifyResult(True, 2, None)


def test_verify_returns_first_matching_page():
    pages = [SENTENCE, "other", SENTENCE]
    assert verify_quote(SENTENCE, pages).page == 1


def test_verify_rejects_missing_quote():
    result = verify_quote("This Agreement is governed by the laws of France.", [SENTENCE])
    assert result.ok is False
    assert result.page is None
    assert result.reason == "not found verbatim on any single page"


def test_verify_rejects_short_quote():
    quote = "governed by Delaware law"
    assert len(quote.split()) < MIN_QUOTE_WORDS
    result = verify_quote(quote, ["The parties are governed by Delaware law."])
    assert result.ok is False
    assert result.reason == "too short"


def test_verify_rejects_cross_page_quote():
    pages = ["Preamble. This Agreement shall be governed", "by the laws of Delaware. Notices."]
    result = verify_quote(SENTENCE, pages)
    assert result.ok is False
    assert result.reason == "not found verbatim on any single page"


@pytest.mark.parametrize("quote", ["", "   "])
def test_verify_rejects_empty_quote(quote):
    result = verify_quote(quote, [SENTENCE])
    assert result.ok is False
    assert result.reason == "empty quote"


def test_token_f1():
    assert token_f1("a b c d", "a b c d") == 1.0
    assert token_f1("a b", "c d") == 0.0
    assert token_f1("a b c d", "a b") == pytest.approx(0.6667, abs=1e-4)
