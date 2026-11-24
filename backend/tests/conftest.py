import pytest

ENV = {
    "OPENROUTER_API_KEY": "test-key",
    "OPENROUTER_MODEL": "vendor/model:free",
    "LLM_MAX_CONCURRENCY": "2",
    "DATA_DIR": "./data",
    "LLM_CACHE_PATH": "./data/llm_cache.db",
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/app",
    "CHECKPOINT_DB_URL": "postgresql://u:p@localhost:5432/ckpt?sslmode=disable",
    "QDRANT_URL": "http://localhost:6333",
}


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def make_pdf():
    import pymupdf

    def build(pages: list[str], *, blank: bool = False) -> bytes:
        doc = pymupdf.open()
        for text in pages:
            page = doc.new_page()
            if not blank:
                page.insert_textbox(pymupdf.Rect(50, 50, 545, 792), text, fontsize=11)
        data = doc.tobytes()
        doc.close()
        return data

    return build
