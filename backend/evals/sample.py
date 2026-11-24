import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.ingest.pdf import PdfRejected, parse_pdf
from evals.cuad import GoldLabel


@dataclass(frozen=True)
class EvalContract:
    title: str
    pdf: Path
    page_count: int


def _rejection_reason(exc: PdfRejected) -> str:
    if exc.status_code == 413:
        return "too large"
    if exc.status_code == 422:
        return "too many pages" if "pages" in exc.detail else "no text layer"
    return "unreadable"


def eligible_contracts(
    gold: Mapping[str, Mapping[str, GoldLabel]], matched: Mapping[str, Path]
) -> tuple[list[EvalContract], list[tuple[str, str]]]:
    """Keep only contracts the app would accept, using the same limits as upload."""
    eligible: list[EvalContract] = []
    excluded: list[tuple[str, str]] = []
    for title in sorted(gold):
        pdf = matched.get(title)
        if pdf is None:
            excluded.append((title, "no matching pdf"))
            continue
        try:
            pages = parse_pdf(pdf.read_bytes())
        except PdfRejected as exc:
            excluded.append((title, _rejection_reason(exc)))
        except OSError:
            excluded.append((title, "unreadable"))
        else:
            eligible.append(EvalContract(title, pdf, len(pages)))
    return eligible, excluded


def sample_contracts(
    eligible: Sequence[EvalContract],
    gold: Mapping[str, Mapping[str, GoldLabel]],
    labels: Sequence[str],
    n: int,
    seed: int,
) -> tuple[list[EvalContract], list[str]]:
    """Seeded sample that covers a present and an absent case per label when the data allows."""
    shuffled = sorted(eligible, key=lambda c: c.title)
    random.Random(seed).shuffle(shuffled)

    picked: list[EvalContract] = []
    gaps: list[str] = []
    needs = [(label, True) for label in labels] + [(label, False) for label in labels]
    for label, present in needs:
        if any(gold[c.title][label].present == present for c in picked):
            continue
        candidate = next(
            (c for c in shuffled if c not in picked and gold[c.title][label].present == present),
            None,
        )
        side = "present" if present else "absent"
        if candidate is None:
            gaps.append(f"{label}: no {side} contract available")
        elif len(picked) >= n:
            gaps.append(f"{label}: no {side} contract in the sample (n={n} is too small)")
        else:
            picked.append(candidate)
    for contract in shuffled:
        if len(picked) >= n:
            break
        if contract not in picked:
            picked.append(contract)
    return picked, gaps
