from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class FindingStatus(StrEnum):
    OK = "ok"
    RISKY = "risky"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


class DecisionState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


def _time_column() -> Column:
    return Column(DateTime(timezone=True))


class Contract(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    filename: str
    path: str
    page_count: int
    uploaded_at: datetime = Field(default_factory=utcnow, sa_column=_time_column())


class Run(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    contract_id: str = Field(foreign_key="contract.id", index=True)
    status: str = RunStatus.QUEUED
    started_at: datetime | None = Field(default=None, sa_column=_time_column())
    finished_at: datetime | None = Field(default=None, sa_column=_time_column())
    model: str
    playbook_hash: str


class Finding(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    clause_id: str
    status: str
    severity: str | None = None
    quote: str | None = None
    page: int | None = None
    bboxes_json: list = Field(default_factory=list, sa_column=Column(JSON))
    candidates_json: list = Field(default_factory=list, sa_column=Column(JSON))
    playbook_rule: str
    issues_json: list = Field(default_factory=list, sa_column=Column(JSON))
    rationale: str | None = None
    suggestion_text: str | None = None
    suggestion_explanation: str | None = None
    error: str | None = None
    verify_failures: int = 0


class Decision(SQLModel, table=True):
    finding_id: str = Field(foreign_key="finding.id", primary_key=True)
    state: str = DecisionState.PENDING
    edited_text: str | None = None
    decided_at: datetime = Field(default_factory=utcnow, sa_column=_time_column())
