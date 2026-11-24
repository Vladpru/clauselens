from langchain_community.cache import SQLiteCache
from langchain_openrouter import ChatOpenRouter

from app.config import Settings
from app.llm import LLM_MAX_RETRIES, LLM_MAX_TOKENS, LLM_TIMEOUT_S, get_chat_model


def test_get_chat_model_uses_configured_model(env):
    m = get_chat_model(Settings(_env_file=None))
    assert isinstance(m, ChatOpenRouter)
    assert m.model_name == "vendor/model:free"


def test_get_chat_model_temperature_zero(env):
    m = get_chat_model(Settings(_env_file=None))
    assert m.temperature == 0


def test_cache_enabled_when_path_set(env, monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.db"))
    m = get_chat_model(Settings(_env_file=None))
    assert isinstance(m.cache, SQLiteCache)


def test_cache_disabled_when_path_empty(env, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_PATH", "")
    m = get_chat_model(Settings(_env_file=None))
    assert m.cache is None


def test_cache_creates_missing_parent_dir(env, monkeypatch, tmp_path):
    path = tmp_path / "new" / "dir" / "cache.db"
    monkeypatch.setenv("LLM_CACHE_PATH", str(path))
    get_chat_model(Settings(_env_file=None))
    assert path.parent.is_dir()


def test_fallback_models_are_sent_in_order_with_the_primary_first(env, monkeypatch):
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "vendor/second:free,vendor/third:free")
    m = get_chat_model(Settings(_env_file=None))
    assert m.model_name == "vendor/model:free"
    assert m._default_params["models"] == [
        "vendor/model:free",
        "vendor/second:free",
        "vendor/third:free",
    ]


def test_no_models_param_without_fallbacks(env):
    m = get_chat_model(Settings(_env_file=None))
    assert "models" not in m._default_params


def test_fallback_models_do_not_change_the_llm_cache_key(env, monkeypatch):
    plain = get_chat_model(Settings(_env_file=None))
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "vendor/second:free,vendor/third:free")
    with_fallbacks = get_chat_model(Settings(_env_file=None))
    assert with_fallbacks._get_llm_string() == plain._get_llm_string()


def test_cache_key_still_depends_on_the_primary_model(env, monkeypatch):
    first = get_chat_model(Settings(_env_file=None))
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/other:free")
    second = get_chat_model(Settings(_env_file=None))
    assert first._get_llm_string() != second._get_llm_string()


def test_cache_key_matches_a_plain_chat_openrouter(env):
    """Existing cache rows were written by a plain ChatOpenRouter; they must keep hitting."""
    s = Settings(_env_file=None)
    plain = ChatOpenRouter(
        model=s.openrouter_model,
        api_key=s.openrouter_api_key,
        temperature=0,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT_S * 1000,
        max_retries=LLM_MAX_RETRIES,
    )
    assert get_chat_model(s)._get_llm_string() == plain._get_llm_string()
