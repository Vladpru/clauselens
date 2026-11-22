"""S5: Qdrant hybrid (dense + sparse) retrieval through langchain-qdrant. Usage: s5_hybrid.py"""

import json
import sys
import urllib.request

import pymupdf
import yaml
from fastembed import TextEmbedding
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models

from app.config import REPO_ROOT, get_settings

COLLECTION = "contract_chunks_spike"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
CHUNK_CHARS = 800
CHUNK_OVERLAP = 150
TOP_K = 8


class FastEmbedDense(Embeddings):
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([text]))).tolist()


def chunk_pdf(title: str, pdf_path: str) -> list[Document]:
    docs: list[Document] = []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    with pymupdf.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text()
            for i, start in enumerate(range(0, max(len(text), 1), step)):
                piece = text[start : start + CHUNK_CHARS].strip()
                if piece:
                    metadata = {"contract_id": title, "page": page_number, "chunk_id": f"{page_number}-{i}"}
                    docs.append(Document(page_content=piece, metadata=metadata))
    return docs


def main() -> int:
    settings = get_settings()
    records = json.loads((settings.data_dir / "spikes" / "s3.json").read_text())
    playbook = yaml.safe_load((REPO_ROOT / "playbook" / "playbook.yaml").read_text())
    clause = next(c for c in playbook["clauses"] if c["id"] == "governing_law")
    query = " ".join(clause["query_terms"])

    cache_dir = str(settings.data_dir / "models")
    dense = FastEmbedDense(DENSE_MODEL, cache_dir)
    sparse = FastEmbedSparse(model_name=SPARSE_MODEL, cache_dir=cache_dir)

    docs = [d for r in records for d in chunk_pdf(r["title"], r["pdf"])]
    store = QdrantVectorStore.from_documents(
        docs,
        embedding=dense,
        sparse_embedding=sparse,
        url=settings.qdrant_url,
        collection_name=COLLECTION,
        retrieval_mode=RetrievalMode.HYBRID,
        force_recreate=True,
    )

    results = []
    try:
        for record in records:
            title, gold_page = record["title"], record["gold_page"]
            contract_filter = models.Filter(
                must=[models.FieldCondition(key="metadata.contract_id", match=models.MatchValue(value=title))]
            )
            hits = store.similarity_search(query, k=TOP_K, filter=contract_filter)
            result_pages = [h.metadata["page"] for h in hits]
            foreign = sum(1 for h in hits if h.metadata["contract_id"] != title)
            results.append(
                {
                    "title": title,
                    "gold_page": gold_page,
                    "result_pages": result_pages,
                    "hit": gold_page in result_pages,
                    "gold_rank": result_pages.index(gold_page) + 1 if gold_page in result_pages else None,
                    "foreign_results": foreign,
                    "payload_keys": sorted(
                        QdrantClient(url=settings.qdrant_url)
                        .scroll(COLLECTION, limit=1, with_payload=True)[0][0]
                        .payload
                    ),
                }
            )
        with urllib.request.urlopen(f"{settings.qdrant_url}/collections/{COLLECTION}") as response:
            info = json.load(response)["result"]["config"]["params"]
        print("collection vectors:", json.dumps(info.get("vectors")))
        print("collection sparse_vectors:", json.dumps(info.get("sparse_vectors")))
    finally:
        QdrantClient(url=settings.qdrant_url).delete_collection(COLLECTION)

    (settings.data_dir / "spikes" / "s5.json").write_text(json.dumps(results, indent=2))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "title"}), r["title"][:40])
    ok = len(results) == 3 and all(r["hit"] and r["foreign_results"] == 0 for r in results)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
