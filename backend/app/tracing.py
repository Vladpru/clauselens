import os
from collections.abc import MutableMapping

from langsmith import utils

from app.config import Settings


def configure_tracing(settings: Settings, environ: MutableMapping[str, str] = os.environ) -> bool:
    """Turn LangSmith tracing on or off from Settings; return whether it is on.

    LangChain and LangGraph trace by reading LANGSMITH_* from the process environment, not from
    .env. Settings is the single switch, so it also overrides any stray variable in the shell.
    Tracing needs both the flag and a key, so a missing key never half-enables it.
    """
    key = settings.langsmith_api_key
    enabled = settings.langsmith_tracing and key is not None
    for legacy in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        environ.pop(legacy, None)
    if enabled:
        environ["LANGSMITH_TRACING"] = "true"
        environ["LANGSMITH_API_KEY"] = key.get_secret_value()
        environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        if settings.langsmith_endpoint:
            environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    else:
        environ["LANGSMITH_TRACING"] = "false"
        environ.pop("LANGSMITH_API_KEY", None)
        environ.pop("LANGCHAIN_API_KEY", None)
    utils.get_env_var.cache_clear()
    return enabled
