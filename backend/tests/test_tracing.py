import os

import pytest
from langsmith import utils

from app.config import Settings
from app.tracing import configure_tracing

TRACING_VARS = [
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_tracing_env(monkeypatch):
    for name in TRACING_VARS:
        monkeypatch.delenv(name, raising=False)
    utils.get_env_var.cache_clear()
    yield
    utils.get_env_var.cache_clear()


def settings(monkeypatch, env, **values):
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_enabled_with_key_sets_langsmith_environment(env, monkeypatch):
    s = settings(
        monkeypatch, env, LANGSMITH_TRACING="true", LANGSMITH_API_KEY="ls-key", LANGSMITH_PROJECT="proj"
    )
    assert configure_tracing(s) is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-key"
    assert os.environ["LANGSMITH_PROJECT"] == "proj"
    assert utils.tracing_is_enabled() is True


def test_endpoint_is_passed_through_when_set(env, monkeypatch):
    s = settings(
        monkeypatch, env, LANGSMITH_TRACING="true", LANGSMITH_API_KEY="k", LANGSMITH_ENDPOINT="https://eu.example"
    )
    configure_tracing(s)
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://eu.example"


def test_off_by_default_sends_nothing(env, monkeypatch):
    assert configure_tracing(settings(monkeypatch, env)) is False
    assert utils.tracing_is_enabled() is False


def test_flag_without_key_stays_off(env, monkeypatch):
    s = settings(monkeypatch, env, LANGSMITH_TRACING="true")
    assert configure_tracing(s) is False
    assert utils.tracing_is_enabled() is False


def test_settings_override_tracing_set_in_the_shell(env, monkeypatch):
    """.env is the single switch: a stray shell variable must not enable tracing."""
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "shell-key")
    s = Settings(_env_file=None, langsmith_tracing=False)
    assert configure_tracing(s) is False
    assert utils.tracing_is_enabled() is False
