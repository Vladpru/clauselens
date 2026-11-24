from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator


class UploadResponse(BaseModel):
    contract_id: str
    page_count: int


class AnalyzeResponse(BaseModel):
    run_id: str


class DecisionView(BaseModel):
    state: str
    edited_text: str | None
    decided_at: datetime


class FindingView(BaseModel):
    id: str
    clause_id: str
    clause_title: str
    status: str
    severity: str | None
    quote: str | None
    page: int | None
    bboxes: list[list[float]]
    candidates: list[dict]
    playbook_rule: str
    issues: list[str]
    rationale: str | None
    suggestion_text: str | None
    suggestion_explanation: str | None
    error: str | None
    verify_failures: int
    decision: DecisionView | None


class RunView(BaseModel):
    run_id: str
    contract_id: str
    status: str
    model: str
    started_at: datetime | None
    finished_at: datetime | None
    progress: dict[str, str]
    findings: list[FindingView]


class DecisionIn(BaseModel):
    state: Literal["accepted", "edited", "rejected"]
    edited_text: str | None = None

    @model_validator(mode="after")
    def _check_text(self) -> DecisionIn:
        if self.state == "edited":
            if not (self.edited_text and self.edited_text.strip()):
                raise ValueError("edited_text is required when state is 'edited'")
        else:
            self.edited_text = None
        return self
