from pathlib import Path
from typing import Protocol

from fastembed import TextEmbedding
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from app.ingest.chunk import Chunk

COLLECTION = "contract_chunks"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
DENSE_DIMENSIONS = 384
SPARSE_VECTOR_NAME = "langchain-sparse"
CONTRACT_ID_KEY = "metadata.contract_id"


class Candidate(BaseModel):
    chunk_id: str
    page: int
    text: str


class Retriever(Protocol):
    def search(self, contract_id: str, query: str, k: int) -> list[Candidate]: ...


class FastEmbedDense(Embeddings):
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([text]))).tolist()


def _document_position(candidate: Candidate) -> tuple[int, int]:
    return candidate.page, int(candidate.chunk_id.rsplit("-", 1)[1])


def _contract_filter(contract_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=CONTRACT_ID_KEY, match=models.MatchValue(value=contract_id)
            )
        ]
    )


class ChunkIndex:
    def __init__(
        self, client: QdrantClient, cache_dir: Path, collection_name: str = COLLECTION
    ) -> None:
        self._client = client
        self._collection = collection_name
        if not client.collection_exists(collection_name):
            client.create_collection(
                collection_name,
                vectors_config=models.VectorParams(
                    size=DENSE_DIMENSIONS, distance=models.Distance.COSINE
                ),
                sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
            )
            client.create_payload_index(
                collection_name,
                field_name=CONTRACT_ID_KEY,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        self._store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=FastEmbedDense(DENSE_MODEL, str(cache_dir)),
            sparse_embedding=FastEmbedSparse(model_name=SPARSE_MODEL, cache_dir=str(cache_dir)),
            retrieval_mode=RetrievalMode.HYBRID,
            sparse_vector_name=SPARSE_VECTOR_NAME,
        )

    def add_contract(self, contract_id: str, chunks: list[Chunk]) -> int:
        documents = [
            Document(
                page_content=chunk.text,
                metadata={
                    "contract_id": contract_id,
                    "page": chunk.page,
                    "chunk_id": chunk.chunk_id,
                },
            )
            for chunk in chunks
        ]
        if documents:
            self._store.add_documents(documents)
        return len(documents)

    def search(self, contract_id: str, query: str, k: int) -> list[Candidate]:
        hits = self._store.similarity_search(query, k=k, filter=_contract_filter(contract_id))
        candidates = [
            Candidate(
                chunk_id=hit.metadata["chunk_id"],
                page=hit.metadata["page"],
                text=hit.page_content,
            )
            for hit in hits
        ]
        # Qdrant hybrid ranks vary between identical queries. Document order makes the
        # prompt (and so the LLM cache key) depend only on which chunks were retrieved.
        return sorted(candidates, key=_document_position)

    def delete_contract(self, contract_id: str) -> None:
        self._client.delete(
            self._collection,
            points_selector=models.FilterSelector(filter=_contract_filter(contract_id)),
        )
