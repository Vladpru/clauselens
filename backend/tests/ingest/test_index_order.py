from langchain_core.documents import Document

from app.ingest.index import ChunkIndex


class ShuffledStore:
    def __init__(self, ids: list[str]):
        self.docs = [
            Document(
                page_content=f"text {chunk_id}",
                metadata={"chunk_id": chunk_id, "page": int(chunk_id.split("-")[0])},
            )
            for chunk_id in ids
        ]

    def similarity_search(self, query, k, filter):
        return self.docs[:k]


def index_with(ids: list[str]) -> ChunkIndex:
    index = ChunkIndex.__new__(ChunkIndex)
    index._store = ShuffledStore(ids)
    return index


def test_search_returns_candidates_in_document_order():
    index = index_with(["10-4", "2-0", "10-6", "2-10", "2-9", "9-1"])
    ids = [c.chunk_id for c in index.search("c", "q", 8)]
    assert ids == ["2-0", "2-9", "2-10", "9-1", "10-4", "10-6"]


def test_search_order_is_independent_of_retrieval_rank():
    first = index_with(["3-1", "1-0", "2-5"])
    second = index_with(["2-5", "3-1", "1-0"])
    assert [c.chunk_id for c in first.search("c", "q", 8)] == [
        c.chunk_id for c in second.search("c", "q", 8)
    ]
