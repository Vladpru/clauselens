import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import init_db, make_engine, mark_stale_runs_failed
from app.models import (
    Contract,
    Decision,
    DecisionState,
    Finding,
    FindingStatus,
    Run,
    RunStatus,
)


@pytest.fixture
def session():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        yield session


def add_run(session, status: str) -> Run:
    contract = Contract(filename="c.pdf", path="/tmp/c.pdf", page_count=3)
    session.add(contract)
    session.commit()
    run = Run(contract_id=contract.id, status=status, model="m", playbook_hash="abc")
    session.add(run)
    session.commit()
    return run


def test_create_all_and_roundtrip_finding(session):
    run = add_run(session, RunStatus.COMPLETED)
    finding = Finding(
        run_id=run.id,
        clause_id="governing_law",
        status=FindingStatus.RISKY,
        bboxes_json=[[1.0, 2.0, 3.0, 4.0]],
        candidates_json=[{"chunk_id": "1-0", "page": 1, "text": "t"}],
        issues_json=["issue one"],
        playbook_rule="rule",
        verify_failures=1,
    )
    session.add(finding)
    session.commit()
    session.expunge_all()
    loaded = session.exec(select(Finding)).one()
    assert loaded.bboxes_json == [[1.0, 2.0, 3.0, 4.0]]
    assert loaded.candidates_json == [{"chunk_id": "1-0", "page": 1, "text": "t"}]
    assert loaded.issues_json == ["issue one"]
    assert loaded.verify_failures == 1
    assert loaded.status == "risky"


def test_decision_primary_key_is_finding_id(session):
    run = add_run(session, RunStatus.COMPLETED)
    finding = Finding(run_id=run.id, clause_id="c", status=FindingStatus.RISKY, playbook_rule="r")
    session.add(finding)
    session.commit()
    session.add(Decision(finding_id=finding.id, state=DecisionState.PENDING))
    session.commit()
    session.add(Decision(finding_id=finding.id, state=DecisionState.ACCEPTED))
    with pytest.raises(IntegrityError):
        session.commit()


def test_mark_stale_runs_failed(session):
    running = add_run(session, RunStatus.RUNNING)
    queued = add_run(session, RunStatus.QUEUED)
    completed = add_run(session, RunStatus.COMPLETED)
    assert mark_stale_runs_failed(session) == 2
    session.expire_all()
    assert session.get(Run, running.id).status == "failed"
    assert session.get(Run, running.id).finished_at is not None
    assert session.get(Run, queued.id).status == "failed"
    assert session.get(Run, completed.id).status == "completed"
    assert session.get(Run, completed.id).finished_at is None
