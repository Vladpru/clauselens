from app.graph.nodes import report_step
from app.graph.prompts import assess_messages
from app.graph.state import ClauseAssessment, ClauseState, GraphDeps
from app.graph.structured import StructuredCallError, invoke_structured


def assess(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "assess")
    rule = deps.playbook.clause(state["clause_id"])
    messages = assess_messages(rule, deps.playbook.stance, state["extraction"].quote)
    try:
        return {"assessment": invoke_structured(deps.model, ClauseAssessment, messages)}
    except StructuredCallError as exc:
        return {"error": str(exc)}
