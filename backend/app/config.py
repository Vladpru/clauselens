from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    openrouter_api_key: SecretStr = Field(min_length=1)
    openrouter_model: str = Field(min_length=1)
    openrouter_fallback_models: Annotated[list[str], NoDecode] = []
    llm_max_concurrency: int = 2
    data_dir: Path = Path("data")
    llm_cache_path: Path | None = Path("data/llm_cache.db")
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "clauselens"
    langsmith_endpoint: str | None = None
    database_url: str
    checkpoint_db_url: str
    qdrant_url: str

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @field_validator("openrouter_fallback_models", mode="before")
    @classmethod
    def _split_fallback_models(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _dedupe_fallback_models(self) -> Settings:
        seen = {self.openrouter_model}
        self.openrouter_fallback_models = [
            m for m in self.openrouter_fallback_models if not (m in seen or seen.add(m))
        ]
        return self

    @field_validator("langsmith_api_key", "langsmith_endpoint", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("llm_cache_path", mode="before")
    @classmethod
    def _resolve_llm_cache_path(cls, value: object) -> Path | None:
        if value is None or value == "":
            return None
        path = Path(str(value))
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
