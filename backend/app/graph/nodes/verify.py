from app.graph.nodes import report_step
from app.graph.state import ClauseState, GraphDeps
from app.ingest.normalize import verify_quote
from app.ingest.pdf import load_pages


def verify(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "verify")
    pages = load_pages(deps.contract_dir(state["contract_id"]))
    result = verify_quote(state["extraction"].quote or "", pages)
    if result.ok:
        return {"page": result.page, "feedback": None}
    return {
        "verify_failures": state.get("verify_failures", 0) + 1,
        "feedback": (
            f"quote not found verbatim ({result.reason}); "
            "copy the exact text from one passage"
        ),
    }
