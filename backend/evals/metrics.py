from collections.abc import Sequence
from dataclasses import dataclass

from app.ingest.normalize import normalize, token_f1

SPAN_MATCH_F1 = 0.5
FOUND_STATUSES = {"ok", "risky"}


@dataclass
class ClauseOutcome:
    title: str
    label: str
    gold_present: bool
    status: str
    quote: str | None
    gold_spans: tuple[str, ...]
    verify_failures: int
    error: str | None
    candidate_pages: list[int]
    gold_pages: list[int]

    @property
    def found(self) -> bool:
        """Found means a verified quote was shown; `ok` without a quote is not found."""
        return self.quote is not None and self.status in FOUND_STATUSES


def _for_label(outcomes: Sequence[ClauseOutcome], label: str) -> list[ClauseOutcome]:
    return [o for o in outcomes if o.label == label]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def presence_prf(
    outcomes: Sequence[ClauseOutcome], label: str
) -> tuple[float | None, float | None, float | None, int, int, int]:
    rows = _for_label(outcomes, label)
    tp = sum(1 for o in rows if o.gold_present and o.found)
    fp = sum(1 for o in rows if not o.gold_present and o.found)
    fn = sum(1 for o in rows if o.gold_present and not o.found)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1, tp, fp, fn


def span_match_rate(outcomes: Sequence[ClauseOutcome], label: str) -> float | None:
    true_positives = [o for o in _for_label(outcomes, label) if o.gold_present and o.found]
    matches = sum(
        1
        for o in true_positives
        if max((token_f1(o.quote, span) for span in o.gold_spans), default=0.0) >= SPAN_MATCH_F1
    )
    return _ratio(matches, len(true_positives))


def verification_rejection_rate(outcomes: Sequence[ClauseOutcome]) -> float | None:
    """Among outcomes where the extractor produced a quote, the share whose first quote failed."""
    quoted = [o for o in outcomes if o.quote is not None or o.verify_failures >= 1]
    return _ratio(sum(1 for o in quoted if o.verify_failures >= 1), len(quoted))


def uncertain_rate(outcomes: Sequence[ClauseOutcome]) -> float | None:
    return _ratio(sum(1 for o in outcomes if o.status == "uncertain"), len(outcomes))


def error_rate(outcomes: Sequence[ClauseOutcome]) -> float | None:
    return _ratio(sum(1 for o in outcomes if o.error is not None), len(outcomes))


def retrieval_hit_rate(outcomes: Sequence[ClauseOutcome], label: str) -> float | None:
    present = [o for o in _for_label(outcomes, label) if o.gold_present]
    hits = sum(1 for o in present if set(o.candidate_pages) & set(o.gold_pages))
    return _ratio(hits, len(present))


def gold_pages(pages: Sequence[str], spans: Sequence[str]) -> list[int]:
    """Pages whose normalized text contains any normalized gold span (eval side only)."""
    needles = [n for n in (normalize(s) for s in spans) if n]
    return [
        number
        for number, text in enumerate(pages, start=1)
        if any(needle in normalize(text) for needle in needles)
    ]
