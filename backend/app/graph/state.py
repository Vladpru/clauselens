import operator
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.ingest.index import Candidate, Retriever
from app.ingest.pdf import BBox
from app.playbook import Playbook


class ClauseExtraction(BaseModel):
    """Report whether the clause appears in the passages and quote it exactly."""

    found: bool
    quote: str | None
    reasoning: str


class ClauseAssessment(BaseModel):
    """Judge a quoted clause against the playbook rule."""

    compliant: bool
    issues: list[str]
    rationale: str


class ClauseSuggestion(BaseModel):
    """Propose safer wording for the clause, based on the playbook's preferred wording."""

    text: str
    explanation: str


class FindingResult(BaseModel):
    clause_id: str
    status: str
    severity: str | None = None
    quote: str | None = None
    page: int | None = None
    bboxes: list[BBox] = []
    candidates: list[Candidate] = []
    playbook_rule: str
    issues: list[str] = []
    rationale: str | None = None
    suggestion_text: str | None = None
    suggestion_explanation: str | None = None
    error: str | None = None
    verify_failures: int = 0


class ReviewState(TypedDict):
    run_id: str
    contract_id: str
    clause_ids: list[str]
    findings: Annotated[list[FindingResult], operator.add]
    status: str | None


class ClauseState(TypedDict, total=False):
    contract_id: str
    clause_id: str
    candidates: list[Candidate]
    extraction: ClauseExtraction | None
    feedback: str | None
    verify_failures: int
    page: int | None
    bboxes: list[BBox]
    assessment: ClauseAssessment | None
    suggestion: ClauseSuggestion | None
    error: str | None
    findings: Annotated[list[FindingResult], operator.add]


class ClauseOutput(TypedDict):
    findings: list[FindingResult]


@dataclass(frozen=True)
class GraphDeps:
    model: BaseChatModel
    retriever: Retriever
    playbook: Playbook
    contract_dir: Callable[[str], Path]
    save_findings: Callable[[str, list[FindingResult]], None]
    top_k: int = 8
