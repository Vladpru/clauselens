from typing import Any

from langchain_community.cache import SQLiteCache
from langchain_core.language_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter

from app.config import Settings, get_settings

LLM_MAX_TOKENS = 4096
LLM_TIMEOUT_S = 120
LLM_MAX_RETRIES = 3


class ChatOpenRouterWithFallbacks(ChatOpenRouter):
    """ChatOpenRouter whose LLM cache key ignores the fallback list.

    Fallbacks do not change what the primary model answers, so adding or reordering them
    must not throw away cached responses. The key stays equal to a plain ChatOpenRouter's.
    """

    def _get_llm_string(self, stop: list[str] | None = None, **kwargs: Any) -> str:
        plain = self.model_copy(update={"model_kwargs": {}})
        plain.__class__ = ChatOpenRouter  # same fields; only the serialized class name differs
        return plain._get_llm_string(stop, **kwargs)


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    cache = None
    if settings.llm_cache_path is not None:
        settings.llm_cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = SQLiteCache(database_path=str(settings.llm_cache_path))
    # OpenRouter tries these in order when a model is down or rate limited, so this stays one
    # chat model and structured output keeps working.
    model_kwargs = (
        {"models": [settings.openrouter_model, *settings.openrouter_fallback_models]}
        if settings.openrouter_fallback_models
        else {}
    )
    return ChatOpenRouterWithFallbacks(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        temperature=0,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT_S * 1000,
        max_retries=LLM_MAX_RETRIES,
        cache=cache,
        model_kwargs=model_kwargs,
    )
