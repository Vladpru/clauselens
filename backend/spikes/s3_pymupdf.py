"""S3: PyMuPDF page text and search_for on a known gold quote. Usage: s3_pymupdf.py <cuad_root>"""

import json
import random
import re
import sys
from pathlib import Path

import pymupdf

from app.config import get_settings
from evals.cuad import TARGET_LABELS, index_pdfs, load_gold, match_pdfs

LABEL = "Governing Law"
SAMPLE_SEED = 42
SAMPLE_SIZE = 3
QUOTE_DASH_MAP = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "­": None}
)


def pick_gold_span(spans: list[str] | tuple[str, ...]) -> str:
    """CUAD lists answers out of document order and some are fragments; the longest is the clause."""
    return max(spans, key=len)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def collapse_strict(text: str) -> str:
    return collapse(text.translate(QUOTE_DASH_MAP))


# (step name, normalizer, page text extractor kwargs)
STEPS = (
    ("collapse+casefold", collapse, {}),
    ("quotes/dashes/soft-hyphen", collapse_strict, {}),
    ("quotes/dashes/soft-hyphen + sort=True", collapse_strict, {"sort": True}),
)


def locate(doc: pymupdf.Document, span: str) -> tuple[int | None, bool, str | None]:
    """Return (1-based page, crosses_page, name of the first normalization step that matched)."""
    for name, normalize, kwargs in STEPS:
        needle = normalize(span)
        pages = [normalize(page.get_text(**kwargs)) for page in doc]
        for i, text in enumerate(pages):
            if needle in text:
                return i + 1, False, name
        for i in range(len(pages) - 1):
            if needle in pages[i] + " " + pages[i + 1]:
                return i + 1, True, name
    return None, False, None


def word_rects(page: pymupdf.Page, span: str) -> int:
    """Count rectangles of the first run of consecutive page words equal to the span tokens."""
    tokens = collapse_strict(span).split(" ")
    words = [(collapse_strict(w[4]), pymupdf.Rect(w[:4])) for w in page.get_text("words")]
    texts = [w[0] for w in words]
    for start in range(len(texts) - len(tokens) + 1):
        if texts[start : start + len(tokens)] == tokens:
            return len(tokens)
    return 0


def main(cuad_root: Path) -> int:
    gold = load_gold(cuad_root / "CUAD_v1.json", TARGET_LABELS)
    matched, _ = match_pdfs(gold, index_pdfs(cuad_root))
    titles = sorted(t for t in matched if gold[t][LABEL].present)
    chosen = random.Random(SAMPLE_SEED).sample(titles, SAMPLE_SIZE)

    records = []
    for title in chosen:
        pdf_path = matched[title]
        span = pick_gold_span(gold[title][LABEL].spans)
        with pymupdf.open(pdf_path) as doc:
            empty_pages = [i + 1 for i, page in enumerate(doc) if not page.get_text().strip()]
            gold_page, crosses, step = locate(doc, span)
            search_rects = word_count = 0
            if gold_page is not None:
                page = doc[gold_page - 1]
                search_rects = len(page.search_for(re.sub(r"\s+", " ", span).strip()))
                word_count = word_rects(page, span)
            records.append(
                {
                    "title": title,
                    "pdf": str(pdf_path),
                    "page_count": doc.page_count,
                    "empty_pages": empty_pages,
                    "gold_page": gold_page,
                    "crosses_page": crosses,
                    "normalization_needed": step,
                    "search_for_rects": search_rects,
                    "word_rects": word_count,
                }
            )

    out_dir = get_settings().data_dir / "spikes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "s3.json").write_text(json.dumps(records, indent=2))
    for record in records:
        print(json.dumps({k: v for k, v in record.items() if k != "pdf"}))

    ok = len(records) == SAMPLE_SIZE and all(
        r["gold_page"] is not None and r["empty_pages"] == [] for r in records
    )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
