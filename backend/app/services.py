import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.api.schemas import DecisionView, FindingView, RunView
from app.config import Settings
from app.db import init_db, make_engine
from app.graph.review_graph import build_review_graph, run_config
from app.graph.state import FindingResult, GraphDeps
from app.ingest.chunk import chunk_pages
from app.ingest.index import ChunkIndex, Retriever
from app.ingest.pdf import parse_pdf, save_contract_files
from app.llm import get_chat_model
from app.models import (
    Contract,
    Decision,
    DecisionState,
    Finding,
    Run,
    RunStatus,
    utcnow,
)
from app.playbook import Playbook, load_playbook, playbook_hash
from app.progress import ProgressStore
from app.tracing import configure_tracing

logger = logging.getLogger(__name__)

FINISHED_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_ERRORS,
    RunStatus.FAILED,
}


class ContractIndex(Retriever, Protocol):
    def add_contract(self, contract_id: str, chunks: list) -> int: ...


class FindingNotFound(LookupError):
    pass


class NoSuggestion(ValueError):
    pass


@dataclass
class Services:
    settings: Settings
    engine: Engine
    index: ContractIndex
    model: BaseChatModel
    checkpointer: BaseCheckpointSaver
    playbook: Playbook
    playbook_hash: str
    progress: ProgressStore
    close: Callable[[], None] | None = None

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)


def checkpoint_serde() -> JsonPlusSerializer:
    """Serializer for the graph state; LangGraph will block unlisted types in a future version."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.graph.state", "FindingResult"),
            ("app.graph.state", "ClauseExtraction"),
            ("app.graph.state", "ClauseAssessment"),
            ("app.graph.state", "ClauseSuggestion"),
            ("app.ingest.index", "Candidate"),
        ]
    )


def build_services(settings: Settings) -> Services:
    configure_tracing(settings)
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from qdrant_client import QdrantClient

    engine = make_engine(settings.database_url)
    init_db(engine)
    pool = ConnectionPool(
        settings.checkpoint_db_url,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    checkpointer = PostgresSaver(pool, serde=checkpoint_serde())
    checkpointer.setup()
    return Services(
        settings=settings,
        engine=engine,
        index=ChunkIndex(QdrantClient(url=settings.qdrant_url), settings.data_dir / "models"),
        model=get_chat_model(settings),
        checkpointer=checkpointer,
        playbook=load_playbook(),
        playbook_hash=playbook_hash(),
        progress=ProgressStore(),
        close=pool.close,
    )


def contract_dir(settings: Settings, contract_id: str) -> Path:
    return settings.data_dir / "contracts" / contract_id


def ingest_contract(svc: Services, filename: str, data: bytes) -> Contract:
    pages = parse_pdf(data)
    contract = Contract(filename=filename, path="", page_count=len(pages))
    directory = contract_dir(svc.settings, contract.id)
    try:
        contract.path = str(save_contract_files(directory, data, pages))
        svc.index.add_contract(contract.id, chunk_pages(pages))
        with svc.session() as session:
            session.add(contract)
            session.commit()
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return contract


def create_run(svc: Services, contract_id: str) -> Run:
    with svc.session() as session:
        if session.get(Contract, contract_id) is None:
            raise LookupError(contract_id)
        run = Run(
            contract_id=contract_id,
            status=RunStatus.QUEUED,
            model=svc.settings.openrouter_model,
            playbook_hash=svc.playbook_hash,
        )
        session.add(run)
        session.commit()
        return run


def _set_run(svc: Services, run_id: str, **fields) -> None:
    with svc.session() as session:
        run = session.get(Run, run_id)
        for name, value in fields.items():
            setattr(run, name, value)
        session.commit()


def execute_run(
    svc: Services,
    run_id: str,
    callbacks: list[BaseCallbackHandler] | None = None,
    tags: list[str] | None = None,
) -> None:
    try:
        with svc.session() as session:
            contract_id = session.get(Run, run_id).contract_id
        _set_run(svc, run_id, status=RunStatus.RUNNING, started_at=utcnow())
        deps = GraphDeps(
            model=svc.model,
            retriever=svc.index,
            playbook=svc.playbook,
            contract_dir=partial(contract_dir, svc.settings),
            save_findings=partial(save_findings, svc),
        )
        graph = build_review_graph(deps, svc.checkpointer)
        config: RunnableConfig = run_config(run_id, svc.settings.llm_max_concurrency)
        if callbacks:
            config["callbacks"] = callbacks
        config["run_name"] = f"review {run_id[:8]}"
        config["tags"] = ["clauselens", *(tags or [])]
        config["metadata"] = {
            "run_id": run_id,
            "contract_id": contract_id,
            "model": svc.settings.openrouter_model,
            "playbook_hash": svc.playbook_hash,
        }
        graph_input = {
            "run_id": run_id,
            "contract_id": contract_id,
            "clause_ids": [rule.id for rule in svc.playbook.clauses],
        }
        for _, event in graph.stream(
            graph_input, config, stream_mode="custom", subgraphs=True
        ):
            svc.progress.set(run_id, event["clause_id"], event["step"])
        status = graph.get_state(config).values.get("status")
        _set_run(
            svc,
            run_id,
            status=status or RunStatus.FAILED,
            finished_at=utcnow(),
        )
    except Exception:
        logger.exception("run %s failed", run_id)
        _set_run(svc, run_id, status=RunStatus.FAILED, finished_at=utcnow())


def save_findings(svc: Services, run_id: str, results: list[FindingResult]) -> None:
    with svc.session() as session:
        for result in results:
            finding = Finding(
                run_id=run_id,
                clause_id=result.clause_id,
                status=result.status,
                severity=result.severity,
                quote=result.quote,
                page=result.page,
                bboxes_json=[list(box) for box in result.bboxes],
                candidates_json=[c.model_dump() for c in result.candidates],
                playbook_rule=result.playbook_rule,
                issues_json=result.issues,
                rationale=result.rationale,
                suggestion_text=result.suggestion_text,
                suggestion_explanation=result.suggestion_explanation,
                error=result.error,
                verify_failures=result.verify_failures,
            )
            session.add(finding)
            session.flush()
            if finding.suggestion_text:
                session.add(Decision(finding_id=finding.id, state=DecisionState.PENDING))
        session.commit()


def _finding_view(svc: Services, finding: Finding, decision: Decision | None) -> FindingView:
    return FindingView(
        id=finding.id,
        clause_id=finding.clause_id,
        clause_title=svc.playbook.clause(finding.clause_id).title,
        status=finding.status,
        severity=finding.severity,
        quote=finding.quote,
        page=finding.page,
        bboxes=finding.bboxes_json,
        candidates=finding.candidates_json,
        playbook_rule=finding.playbook_rule,
        issues=finding.issues_json,
        rationale=finding.rationale,
        suggestion_text=finding.suggestion_text,
        suggestion_explanation=finding.suggestion_explanation,
        error=finding.error,
        verify_failures=finding.verify_failures,
        decision=(
            DecisionView(
                state=decision.state,
                edited_text=decision.edited_text,
                decided_at=decision.decided_at,
            )
            if decision
            else None
        ),
    )


def get_run_view(svc: Services, run_id: str) -> RunView | None:
    with svc.session() as session:
        run = session.get(Run, run_id)
        if run is None:
            return None
        views: list[FindingView] = []
        if run.status in FINISHED_STATUSES:
            rows = session.exec(
                select(Finding, Decision)
                .join(Decision, col(Decision.finding_id) == col(Finding.id), isouter=True)
                .where(Finding.run_id == run_id)
            ).all()
            order = {rule.id: i for i, rule in enumerate(svc.playbook.clauses)}
            rows = sorted(rows, key=lambda row: order.get(row[0].clause_id, len(order)))
            views = [_finding_view(svc, finding, decision) for finding, decision in rows]
        return RunView(
            run_id=run.id,
            contract_id=run.contract_id,
            status=run.status,
            model=run.model,
            started_at=run.started_at,
            finished_at=run.finished_at,
            progress=svc.progress.get(run_id),
            findings=views,
        )


def set_decision(
    svc: Services, finding_id: str, state: str, edited_text: str | None
) -> Decision:
    with svc.session() as session:
        finding = session.get(Finding, finding_id)
        if finding is None:
            raise FindingNotFound(finding_id)
        if not finding.suggestion_text:
            raise NoSuggestion(finding_id)
        decision = session.get(Decision, finding_id) or Decision(finding_id=finding_id)
        decision.state = state
        decision.edited_text = edited_text
        decision.decided_at = utcnow()
        session.add(decision)
        session.commit()
        return decision
