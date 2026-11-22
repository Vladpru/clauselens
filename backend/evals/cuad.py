import json
import logging
import unicodedata
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

TARGET_LABELS: tuple[str, ...] = (
    "Governing Law",
    "Termination For Convenience",
    "Cap On Liability",
    "Non-Compete",
    "Anti-Assignment",
)


@dataclass(frozen=True)
class GoldLabel:
    title: str
    label: str
    present: bool
    spans: tuple[str, ...]


def _label_of(qa_id: str) -> str:
    return qa_id.rsplit("__", 1)[-1]


def load_gold(json_path: Path, labels: Collection[str]) -> dict[str, dict[str, GoldLabel]]:
    contracts = json.loads(Path(json_path).read_text())["data"]
    seen = {
        _label_of(qa["id"])
        for contract in contracts
        for paragraph in contract["paragraphs"]
        for qa in paragraph["qas"]
    }
    unknown = sorted(set(labels) - seen)
    if unknown:
        raise ValueError(f"labels not found in {json_path}: {unknown}")

    gold: dict[str, dict[str, GoldLabel]] = {}
    for contract in contracts:
        title = contract["title"]
        spans: dict[str, list[str]] = {label: [] for label in labels}
        for paragraph in contract["paragraphs"]:
            for qa in paragraph["qas"]:
                label = _label_of(qa["id"])
                if label not in spans:
                    continue
                spans[label].extend(a["text"].strip() for a in qa["answers"] if a["text"].strip())
        gold[title] = {
            label: GoldLabel(title, label, bool(found), tuple(found))
            for label, found in spans.items()
        }
    return gold


def index_pdfs(cuad_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted(Path(cuad_root).rglob("*")):
        if path.suffix.lower() != ".pdf":
            continue
        if path.stem in index:
            raise ValueError(f"duplicate PDF stem {path.stem!r}: {index[path.stem]} and {path}")
        index[path.stem] = path
    return index


def _normalize(name: str) -> str:
    return unicodedata.normalize("NFC", name).strip().casefold()


def match_pdfs(
    titles: Iterable[str], pdf_index: Mapping[str, Path]
) -> tuple[dict[str, Path], list[str]]:
    """Exact stem, then normalized (NFC, strip, casefold), then a unique prefix match.

    A PDF matched in the first two passes is never taken by the prefix pass, and a PDF
    wanted by two prefix matches is given to neither title.
    """
    titles = list(titles)
    normalized: dict[str, list[tuple[str, Path]]] = {}
    for stem, path in pdf_index.items():
        normalized.setdefault(_normalize(stem), []).append((stem, path))

    matched: dict[str, Path] = {}
    pending: list[str] = []
    for title in titles:
        if title in pdf_index:
            matched[title] = pdf_index[title]
            continue
        candidates = normalized.get(_normalize(title), [])
        if len(candidates) == 1:
            matched[title] = candidates[0][1]
        elif not candidates:
            pending.append(title)

    claimed = set(matched.values())
    prefix_pick: dict[str, tuple[str, Path]] = {}
    for title in pending:
        key = _normalize(title)
        if not key:
            continue
        candidates = [
            (stem, path)
            for stem_key, entries in normalized.items()
            if stem_key and (stem_key.startswith(key) or key.startswith(stem_key))
            for stem, path in entries
            if path not in claimed
        ]
        if len(candidates) == 1:
            prefix_pick[title] = candidates[0]

    wanted = Counter(path for _, path in prefix_pick.values())
    for title, (stem, path) in prefix_pick.items():
        if wanted[path] == 1:
            matched[title] = path
            logger.info("prefix match: %r -> %r", title, stem)

    unmatched = [title for title in titles if title not in matched]
    return {title: matched[title] for title in titles if title in matched}, unmatched
