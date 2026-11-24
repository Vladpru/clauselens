import time

import pytest

from app.graph.state import GraphDeps
from app.ingest.chunk import chunk_pages
from app.ingest.index import Candidate
from app.ingest.pdf import parse_pdf, save_contract_files
from app.playbook import load_playbook
from tests.fakes import FakeRetriever, ScriptedChatModel, clause_of
from tests.scripted import PAGES, default_reply


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)


@pytest.fixture
def pages():
    return PAGES


@pytest.fixture
def contract_dir(tmp_path, make_pdf):
    data = make_pdf(PAGES)
    save_contract_files(tmp_path, data, parse_pdf(data))
    return tmp_path


@pytest.fixture
def script():
    """Per (tool name, clause id) overrides: a dict, an exception, a callable, or a list consumed in order."""
    return {}


@pytest.fixture
def make_deps(contract_dir, script):
    def build(retriever=None) -> GraphDeps:
        def responder(tool, messages):
            clause = clause_of(messages)
            entry = script.get((tool, clause), script.get((tool, None)))
            if isinstance(entry, list):
                entry = entry.pop(0)
            if callable(entry):
                entry = entry(messages)
            return default_reply(tool, clause) if entry is None else entry

        candidates = [
            Candidate(chunk_id=c.chunk_id, page=c.page, text=c.text) for c in chunk_pages(PAGES)
        ]
        return GraphDeps(
            model=ScriptedChatModel(responder=responder),
            retriever=retriever if retriever is not None else FakeRetriever(default=candidates),
            playbook=load_playbook(),
            contract_dir=lambda contract_id: contract_dir,
            save_findings=lambda run_id, findings: None,
        )

    return build


@pytest.fixture
def deps(make_deps):
    return make_deps()
