import pytest
from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingest.chunk import chunk_pages
from app.ingest.index import ChunkIndex
from app.playbook import load_playbook

pytestmark = pytest.mark.integration

TEST_COLLECTION = "contract_chunks_test"
FILLER = "The parties agree to the schedules and the payment terms set out in this agreement. " * 8
GOVERNING = "This Agreement shall be construed in accordance with the laws of the State of New York."


def pages_for(marker: str, governing_page: int | None = None) -> list[str]:
    pages = [f"{marker} page {i}. {FILLER}" for i in range(1, 5)]
    if governing_page is not None:
        pages[governing_page - 1] = f"{marker} page {governing_page}. {GOVERNING} {FILLER}"
    return pages


@pytest.fixture(scope="module")
def client():
    client = QdrantClient(url=get_settings().qdrant_url)
    if client.collection_exists(TEST_COLLECTION):
        client.delete_collection(TEST_COLLECTION)
    yield client
    client.delete_collection(TEST_COLLECTION)


@pytest.fixture(scope="module")
def index(client):
    return ChunkIndex(client, get_settings().data_dir / "models", collection_name=TEST_COLLECTION)


def test_hybrid_search_returns_page_of_clause(index):
    index.add_contract("contract-a", chunk_pages(pages_for("alpha", governing_page=3)))
    query = " ".join(load_playbook().clause("governing_law").query_terms)
    results = index.search("contract-a", query, 8)
    assert 3 in [c.page for c in results]


def texts_of(client, contract_id: str) -> set[str]:
    points, _ = client.scroll(
        TEST_COLLECTION,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.contract_id", match=models.MatchValue(value=contract_id)
                )
            ]
        ),
        limit=1000,
        with_payload=True,
    )
    return {p.payload["page_content"] for p in points}


def test_search_is_filtered_by_contract(client, index):
    index.add_contract("contract-a", chunk_pages(pages_for("alpha", governing_page=3)))
    index.add_contract("contract-b", chunk_pages(pages_for("bravo", governing_page=2)))
    results = index.search("contract-a", "construed in accordance with the laws", 8)
    assert results
    own, foreign = texts_of(client, "contract-a"), texts_of(client, "contract-b")
    assert {c.text for c in results} <= own
    assert not {c.text for c in results} & foreign


def test_delete_contract_removes_points(index):
    index.add_contract("contract-c", chunk_pages(pages_for("charlie", governing_page=1)))
    assert index.search("contract-c", "laws of the State of New York", 8)
    index.delete_contract("contract-c")
    assert index.search("contract-c", "laws of the State of New York", 8) == []


def test_search_results_are_in_document_order(index):
    index.add_contract("contract-d", chunk_pages(pages_for("delta", governing_page=3)))
    for _ in range(3):
        results = index.search("contract-d", "construed in accordance with the laws", 8)
        positions = [(c.page, int(c.chunk_id.rsplit("-", 1)[1])) for c in results]
        assert positions == sorted(positions)
