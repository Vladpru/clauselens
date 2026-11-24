import pymupdf
import pytest

from app.ingest.pdf import (
    MAX_BYTES,
    PdfRejected,
    find_quote_rects,
    load_pages,
    parse_pdf,
    save_contract_files,
)

FILLER = "The parties agree to the terms of this agreement and its schedules. " * 5
SENTENCE = "This Agreement shall be governed by the laws of the State of Delaware."
LONG_SENTENCE = (
    "Neither party may assign or transfer this Agreement without the prior written consent "
    "of the other party's counsel, such consent not to be unreasonably withheld or delayed by either "
    "party under any circumstances whatsoever."
)


def test_parse_returns_page_texts(make_pdf):
    data = make_pdf([FILLER + f" marker{i}" for i in range(1, 4)])
    pages = parse_pdf(data)
    assert len(pages) == 3
    assert "marker2" in pages[1]


def test_rejects_non_pdf():
    with pytest.raises(PdfRejected) as exc:
        parse_pdf(b"hello")
    assert exc.value.status_code == 415


def test_rejects_oversized():
    with pytest.raises(PdfRejected) as exc:
        parse_pdf(b"%PDF-" + b"0" * (MAX_BYTES + 1))
    assert exc.value.status_code == 413


def test_rejects_too_many_pages(make_pdf):
    with pytest.raises(PdfRejected) as exc:
        parse_pdf(make_pdf([FILLER] * 101))
    assert exc.value.status_code == 422
    assert "100" in exc.value.detail


def test_rejects_scanned_pdf(make_pdf):
    with pytest.raises(PdfRejected) as exc:
        parse_pdf(make_pdf(["", ""], blank=True))
    assert exc.value.status_code == 422
    assert "text layer" in exc.value.detail


def test_rejects_corrupt_pdf():
    with pytest.raises(PdfRejected) as exc:
        parse_pdf(b"%PDF-1.7 garbage")
    assert exc.value.status_code == 415


def test_save_and_load_pages_roundtrip(tmp_path, make_pdf):
    data = make_pdf([FILLER, FILLER + " second"])
    pages = parse_pdf(data)
    pdf_path = save_contract_files(tmp_path, data, pages)
    assert pdf_path == tmp_path / "original.pdf"
    assert pdf_path.read_bytes() == data
    assert (tmp_path / "pages.json").exists()
    assert load_pages(tmp_path) == pages


def test_find_quote_rects_single_line(tmp_path, make_pdf):
    data = make_pdf([FILLER, SENTENCE])
    pdf_path = save_contract_files(tmp_path, data, parse_pdf(data))
    rects = find_quote_rects(pdf_path, 2, SENTENCE)
    assert len(rects) >= 1
    with pymupdf.open(pdf_path) as doc:
        bounds = doc[1].rect
    for x0, y0, x1, y1 in rects:
        assert bounds.x0 <= x0 < x1 <= bounds.x1
        assert bounds.y0 <= y0 < y1 <= bounds.y1


def test_find_quote_rects_multi_line_falls_back_to_words(tmp_path, make_pdf):
    data = make_pdf([FILLER, LONG_SENTENCE])
    pdf_path = save_contract_files(tmp_path, data, parse_pdf(data))
    quote = LONG_SENTENCE.replace("'", "\u2019")
    assert len(find_quote_rects(pdf_path, 2, quote)) >= 2


def test_find_quote_rects_not_found_returns_empty(tmp_path, make_pdf):
    data = make_pdf([FILLER, SENTENCE])
    pdf_path = save_contract_files(tmp_path, data, parse_pdf(data))
    assert find_quote_rects(pdf_path, 2, "this text is not on the page at all") == []
