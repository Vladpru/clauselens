import pytest

ENV = {
    "OPENROUTER_API_KEY": "test-key",
    "OPENROUTER_MODEL": "vendor/model:free",
    "LLM_MAX_CONCURRENCY": "2",
    "DATA_DIR": "./data",
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/app",
    "CHECKPOINT_DB_URL": "postgresql://u:p@localhost:5432/ckpt?sslmode=disable",
    "QDRANT_URL": "http://localhost:6333",
}


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
