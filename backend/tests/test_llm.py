from langchain_openrouter import ChatOpenRouter

from app.config import Settings
from app.llm import get_chat_model


def test_get_chat_model_uses_configured_model(env):
    m = get_chat_model(Settings(_env_file=None))
    assert isinstance(m, ChatOpenRouter)
    assert m.model_name == "vendor/model:free"


def test_get_chat_model_temperature_zero(env):
    m = get_chat_model(Settings(_env_file=None))
    assert m.temperature == 0
