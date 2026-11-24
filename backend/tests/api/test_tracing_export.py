import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import utils

from app.config import Settings
from app.services import create_run, execute_run
from app.tracing import configure_tracing


class Collector(BaseHTTPRequestHandler):
    requests: ClassVar[list[tuple[str, bytes]]] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Collector.requests.append((self.path, body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture
def endpoint(monkeypatch):
    Collector.requests = []
    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LANGSMITH_DISABLE_RUN_COMPRESSION", "true")
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def reset_tracing(monkeypatch):
    yield
    for name in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    utils.get_env_var.cache_clear()


def run_once(services, contract_id):
    run = create_run(services, contract_id)
    execute_run(services, run.id, tags=["eval"])
    wait_for_all_tracers()
    return run


def sent_text() -> str:
    return b"\n".join(body for _, body in Collector.requests).decode("utf-8", "replace")


def test_enabled_tracing_sends_the_run_tree(services, contract_id, endpoint, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-test-key")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", endpoint)
    monkeypatch.setenv("LANGSMITH_PROJECT", "clauselens-test")
    assert configure_tracing(Settings(_env_file=None)) is True

    run = run_once(services, contract_id)

    text = sent_text()
    assert Collector.requests, "no trace request reached the endpoint"
    assert f"review {run.id[:8]}" in text
    for node in ("retrieve", "extract", "verify", "locate", "assess", "emit"):
        assert node in text
    assert "ScriptedChatModel" in text or "scripted-chat-model" in text
    assert run.id in text
    assert "clauselens-test" in text


def test_disabled_tracing_sends_nothing(services, contract_id, endpoint, monkeypatch):
    monkeypatch.setenv("LANGSMITH_ENDPOINT", endpoint)
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-test-key")
    assert configure_tracing(Settings(_env_file=None)) is False

    run_once(services, contract_id)

    assert Collector.requests == []
