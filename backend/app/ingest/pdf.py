import json
from pathlib import Path

import pymupdf

from app.ingest.normalize import normalize

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
MIN_TEXT_CHARS_PER_PAGE = 100

BBox = tuple[float, float, float, float]


class PdfRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def parse_pdf(data: bytes) -> list[str]:
    if len(data) > MAX_BYTES:
        raise PdfRejected(413, f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not data.startswith(b"%PDF-"):
        raise PdfRejected(415, "File is not a PDF")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfRejected(415, "File could not be read as a PDF") from exc
    with doc:
        if doc.page_count > MAX_PAGES:
            raise PdfRejected(422, f"PDF has more than {MAX_PAGES} pages")
        pages = [page.get_text() for page in doc]
    if not pages:
        raise PdfRejected(422, "PDF has no pages")
    chars = sum(len("".join(text.split())) for text in pages)
    if chars / len(pages) < MIN_TEXT_CHARS_PER_PAGE:
        raise PdfRejected(422, "PDF has no usable text layer (scanned PDFs are not supported)")
    return pages


def save_contract_files(contract_dir: Path, data: bytes, pages: list[str]) -> Path:
    contract_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = contract_dir / "original.pdf"
    pdf_path.write_bytes(data)
    payload = [{"page": number, "text": text} for number, text in enumerate(pages, start=1)]
    (contract_dir / "pages.json").write_text(json.dumps(payload))
    return pdf_path


def load_pages(contract_dir: Path) -> list[str]:
    payload = json.loads((contract_dir / "pages.json").read_text())
    return [entry["text"] for entry in payload]


def find_quote_rects(pdf_path: Path, page: int, quote: str) -> list[BBox]:
    with pymupdf.open(pdf_path) as doc:
        pdf_page = doc[page - 1]
        found = pdf_page.search_for(" ".join(quote.split()))
        if found:
            return [(r.x0, r.y0, r.x1, r.y1) for r in found]
        return _word_rects(pdf_page, quote)


def _word_rects(pdf_page: pymupdf.Page, quote: str) -> list[BBox]:
    """Match consecutive page words against the normalized quote tokens, one rect per text line."""
    tokens = normalize(quote).split()
    if not tokens:
        return []
    words = pdf_page.get_text("words")
    texts = [normalize(w[4]) for w in words]
    for start in range(len(texts) - len(tokens) + 1):
        if texts[start : start + len(tokens)] != tokens:
            continue
        lines: dict[tuple[int, int], list[float]] = {}
        for x0, y0, x1, y1, _, block, line, _ in words[start : start + len(tokens)]:
            box = lines.setdefault((block, line), [x0, y0, x1, y1])
            box[0], box[1] = min(box[0], x0), min(box[1], y0)
            box[2], box[3] = max(box[2], x1), max(box[3], y1)
        return [(b[0], b[1], b[2], b[3]) for b in lines.values()]
    return []
