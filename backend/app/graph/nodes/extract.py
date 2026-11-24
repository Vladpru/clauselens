from app.graph.nodes import report_step
from app.graph.prompts import extract_messages
from app.graph.state import ClauseExtraction, ClauseState, GraphDeps
from app.graph.structured import StructuredCallError, invoke_structured


def extract(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "extract")
    candidates = state["candidates"]
    if not candidates:
        return {
            "extraction": ClauseExtraction(found=False, quote=None, reasoning="no candidates")
        }
    rule = deps.playbook.clause(state["clause_id"])
    messages = extract_messages(rule, candidates, state.get("feedback"))
    try:
        return {"extraction": invoke_structured(deps.model, ClauseExtraction, messages)}
    except StructuredCallError as exc:
        return {"error": str(exc)}
