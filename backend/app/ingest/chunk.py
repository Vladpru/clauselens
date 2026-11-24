from collections.abc import Sequence
from dataclasses import dataclass

CHUNK_CHARS = 800
CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    page: int
    text: str


def chunk_pages(pages: Sequence[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    for page_number, text in enumerate(pages, start=1):
        start = 0
        index = 0
        while start < len(text):
            piece = text[start : start + CHUNK_CHARS].strip()
            if piece:
                chunks.append(Chunk(f"{page_number}-{index}", page_number, piece))
            index += 1
            if start + CHUNK_CHARS >= len(text):
                break
            start += step
    return chunks
