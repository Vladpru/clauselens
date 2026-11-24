from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, select

from app import models
from app.models import RunStatus, utcnow


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(url)


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def mark_stale_runs_failed(session: Session) -> int:
    stale = session.exec(
        select(models.Run).where(
            col(models.Run.status).in_([RunStatus.QUEUED, RunStatus.RUNNING])
        )
    ).all()
    for run in stale:
        run.status = RunStatus.FAILED
        run.finished_at = utcnow()
    session.commit()
    return len(stale)
