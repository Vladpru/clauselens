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
