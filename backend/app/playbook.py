import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import REPO_ROOT

PLAYBOOK_PATH = REPO_ROOT / "playbook" / "playbook.yaml"


class PlaybookError(ValueError):
    pass


class ClauseRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    cuad_label: str
    title: str
    query_terms: list[str] = Field(min_length=1)
    requirement: str
    acceptable: list[str]
    red_flags: list[str]
    preferred_wording: str
    severity_if_missing: Literal["low", "medium", "high"]
    absence_is: Literal["ok", "missing"]


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    stance: str
    clauses: list[ClauseRule] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def _unique_ids(self) -> Playbook:
        ids = [c.id for c in self.clauses]
        if len(ids) != len(set(ids)):
            raise ValueError("clause ids must be unique")
        return self

    def clause(self, clause_id: str) -> ClauseRule:
        for rule in self.clauses:
            if rule.id == clause_id:
                return rule
        raise KeyError(clause_id)


def load_playbook(path: Path = PLAYBOOK_PATH) -> Playbook:
    try:
        return Playbook.model_validate(yaml.safe_load(path.read_text()))
    except (ValidationError, yaml.YAMLError) as exc:
        raise PlaybookError(f"{path}: {exc}") from exc


def playbook_hash(path: Path = PLAYBOOK_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
