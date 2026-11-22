from langchain_core.language_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter

from app.config import Settings, get_settings

LLM_MAX_TOKENS = 4096
LLM_TIMEOUT_S = 120
LLM_MAX_RETRIES = 3


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    return ChatOpenRouter(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        temperature=0,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT_S * 1000,
        max_retries=LLM_MAX_RETRIES,
    )
