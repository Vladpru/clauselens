import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings


def test_settings_reads_model_from_env(env):
    s = Settings(_env_file=None)
    assert s.openrouter_model == "vendor/model:free"


def test_settings_requires_api_key(env, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_model(env, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_not_in_repr(env):
    s = Settings(_env_file=None)
    assert "test-key" not in repr(s)
    assert "test-key" not in str(s.model_dump())


def test_relative_data_dir_resolves_to_repo_root(env, monkeypatch, tmp_path):
    assert Settings(_env_file=None).data_dir == REPO_ROOT / "data"
    monkeypatch.chdir(tmp_path)
    assert Settings(_env_file=None).data_dir == REPO_ROOT / "data"


@pytest.mark.parametrize("name", ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"])
def test_settings_rejects_empty_value(env, monkeypatch, name):
    monkeypatch.setenv(name, "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_cache_path_resolves_to_repo_root(env):
    s = Settings(_env_file=None)
    assert s.llm_cache_path == REPO_ROOT / "data" / "llm_cache.db"


def test_empty_llm_cache_path_disables_cache(env, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_PATH", "")
    assert Settings(_env_file=None).llm_cache_path is None


def test_fallback_models_parse_comma_separated_in_order(env, monkeypatch):
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", " vendor/second:free , vendor/third:free ,,")
    s = Settings(_env_file=None)
    assert s.openrouter_fallback_models == ["vendor/second:free", "vendor/third:free"]


def test_fallback_models_default_to_none(env):
    assert Settings(_env_file=None).openrouter_fallback_models == []


def test_fallback_models_drop_the_primary_and_duplicates(env, monkeypatch):
    monkeypatch.setenv(
        "OPENROUTER_FALLBACK_MODELS", "vendor/model:free,vendor/second:free,vendor/second:free"
    )
    assert Settings(_env_file=None).openrouter_fallback_models == ["vendor/second:free"]


def test_tracing_is_off_by_default(env):
    s = Settings(_env_file=None)
    assert s.langsmith_tracing is False
    assert s.langsmith_api_key is None
    assert s.langsmith_project == "clauselens"
    assert s.langsmith_endpoint is None


def test_langsmith_settings_read_from_env(env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-secret")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-project")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    s = Settings(_env_file=None)
    assert s.langsmith_tracing is True
    assert s.langsmith_api_key.get_secret_value() == "ls-secret"
    assert s.langsmith_project == "my-project"
    assert s.langsmith_endpoint == "https://eu.api.smith.langchain.com"
    assert "ls-secret" not in repr(s)


def test_empty_langsmith_values_mean_unset(env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "")
    s = Settings(_env_file=None)
    assert s.langsmith_api_key is None
    assert s.langsmith_endpoint is None
