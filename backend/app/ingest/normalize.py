import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

MIN_QUOTE_WORDS = 5

_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_WHITESPACE = re.compile(r"\s+")
_CHAR_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "−": "-",
    }
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = text.translate(_CHAR_MAP)
    return _WHITESPACE.sub(" ", text).strip().casefold()


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    page: int | None
    reason: str | None


def verify_quote(quote: str, pages: Sequence[str]) -> VerifyResult:
    needle = normalize(quote)
    if not needle:
        return VerifyResult(False, None, "empty quote")
    if len(needle.split()) < MIN_QUOTE_WORDS:
        return VerifyResult(False, None, "too short")
    for number, page_text in enumerate(pages, start=1):
        if needle in normalize(page_text):
            return VerifyResult(True, number, None)
    return VerifyResult(False, None, "not found verbatim on any single page")


def token_f1(a: str, b: str) -> float:
    tokens_a = normalize(a).split()
    tokens_b = normalize(b).split()
    overlap = sum((Counter(tokens_a) & Counter(tokens_b)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(tokens_a)
    recall = overlap / len(tokens_b)
    return 2 * precision * recall / (precision + recall)
