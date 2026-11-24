from langgraph.config import get_stream_writer

from app.graph.state import ClauseState


def report_step(state: ClauseState, step: str) -> None:
    get_stream_writer()({"clause_id": state["clause_id"], "step": step})
