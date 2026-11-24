from app.graph.nodes import report_step
from app.graph.prompts import suggest_messages
from app.graph.state import ClauseState, ClauseSuggestion, GraphDeps
from app.graph.structured import StructuredCallError, invoke_structured


def suggest(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "suggest")
    rule = deps.playbook.clause(state["clause_id"])
    extraction = state["extraction"]
    quote = extraction.quote if extraction.found else None
    messages = suggest_messages(rule, deps.playbook.stance, quote)
    try:
        return {"suggestion": invoke_structured(deps.model, ClauseSuggestion, messages)}
    except StructuredCallError as exc:
        return {"error": str(exc)}
