import time

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlmodel import Session

from app.config import Settings
from app.db import init_db, make_engine
from app.ingest.chunk import chunk_pages
from app.ingest.index import Candidate
from app.main import create_app
from app.playbook import load_playbook, playbook_hash
from app.progress import ProgressStore
from app.services import Services
from tests.fakes import FakeRetriever, ScriptedChatModel, clause_of
from tests.scripted import PAGES, default_reply


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)


@pytest.fixture
def script():
    return {}


@pytest.fixture
def services(env, monkeypatch, tmp_path, script):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings(_env_file=None)

    def responder(tool, messages):
        clause = clause_of(messages)
        entry = script.get((tool, clause))
        if callable(entry):
            entry = entry(messages)
        return default_reply(tool, clause) if entry is None else entry

    candidates = [Candidate(chunk_id=c.chunk_id, page=c.page, text=c.text) for c in chunk_pages(PAGES)]
    engine = make_engine("sqlite://")
    init_db(engine)
    return Services(
        settings=settings,
        engine=engine,
        index=FakeRetriever(default=candidates),
        model=ScriptedChatModel(responder=responder),
        checkpointer=InMemorySaver(),
        playbook=load_playbook(),
        playbook_hash=playbook_hash(),
        progress=ProgressStore(),
    )


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as client:
        yield client


@pytest.fixture
def db(services):
    with Session(services.engine) as session:
        yield session


@pytest.fixture
def contract_id(client, make_pdf):
    response = client.post(
        "/api/contracts", files={"file": ("c.pdf", make_pdf(PAGES[:3]), "application/pdf")}
    )
    assert response.status_code == 200, response.text
    return response.json()["contract_id"]


@pytest.fixture
def run_id(client, contract_id):
    response = client.post(f"/api/contracts/{contract_id}/analyze")
    assert response.status_code == 202
    return response.json()["run_id"]
