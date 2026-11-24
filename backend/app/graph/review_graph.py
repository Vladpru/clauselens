from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.graph.clause_graph import build_clause_graph
from app.graph.state import GraphDeps, ReviewState
from app.ingest.pdf import load_pages


class ContractUnreadable(Exception):
    pass


def run_config(run_id: str, max_concurrency: int) -> RunnableConfig:
    return {"configurable": {"thread_id": run_id}, "max_concurrency": max_concurrency}


def build_review_graph(deps: GraphDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    def ingest(state: ReviewState) -> dict:
        try:
            pages = load_pages(deps.contract_dir(state["contract_id"]))
        except (OSError, ValueError, KeyError) as exc:
            raise ContractUnreadable(f"no parsed pages for contract {state['contract_id']}") from exc
        if not pages:
            raise ContractUnreadable(f"contract {state['contract_id']} has no pages")
        return {}

    def dispatch(state: ReviewState) -> list[Send]:
        return [
            Send(
                "review_clause",
                {"contract_id": state["contract_id"], "clause_id": clause_id, "verify_failures": 0},
            )
            for clause_id in state["clause_ids"]
        ]

    def finalize(state: ReviewState) -> dict:
        deps.save_findings(state["run_id"], state["findings"])
        has_error = any(finding.error for finding in state["findings"])
        return {"status": "completed_with_errors" if has_error else "completed"}

    graph = StateGraph(ReviewState)
    graph.add_node("ingest", ingest)
    graph.add_node("review_clause", build_clause_graph(deps))
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "ingest")
    graph.add_conditional_edges("ingest", dispatch, ["review_clause"])
    graph.add_edge("review_clause", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
