from app.graph.nodes import report_step
from app.graph.state import ClauseState, FindingResult, GraphDeps
from app.models import FindingStatus
from app.playbook import ClauseRule


def emit(state: ClauseState, *, deps: GraphDeps) -> dict:
    report_step(state, "done")
    rule = deps.playbook.clause(state["clause_id"])
    return {"findings": [_build_finding(state, rule)]}


def _build_finding(state: ClauseState, rule: ClauseRule) -> FindingResult:
    extraction = state.get("extraction")
    assessment = state.get("assessment")
    suggestion = state.get("suggestion")
    error = state.get("error")
    base = {
        "clause_id": rule.id,
        "playbook_rule": rule.requirement,
        "candidates": state.get("candidates", []),
        "verify_failures": state.get("verify_failures", 0),
        "error": error,
    }

    not_found = extraction is not None and not extraction.found
    missing = not_found and rule.absence_is == "missing"
    risky = assessment is not None and not assessment.compliant
    if risky:
        return _risky(state, base, assessment, suggestion)
    if missing:
        return _missing(rule, base, extraction, suggestion)
    if error:
        return FindingResult(status=FindingStatus.UNCERTAIN, **base)
    if not_found:
        return FindingResult(status=FindingStatus.OK, rationale=extraction.reasoning, **base)
    if assessment is not None:
        return FindingResult(
            status=FindingStatus.OK,
            quote=extraction.quote,
            page=state["page"],
            bboxes=state.get("bboxes", []),
            rationale=assessment.rationale,
            **base,
        )
    return FindingResult(status=FindingStatus.UNCERTAIN, **base)


def _risky(state, base, assessment, suggestion) -> FindingResult:
    return FindingResult(
        status=FindingStatus.RISKY,
        quote=state["extraction"].quote,
        page=state["page"],
        bboxes=state.get("bboxes", []),
        issues=assessment.issues,
        rationale=assessment.rationale,
        suggestion_text=suggestion.text if suggestion else None,
        suggestion_explanation=suggestion.explanation if suggestion else None,
        **base,
    )


def _missing(rule, base, extraction, suggestion) -> FindingResult:
    return FindingResult(
        status=FindingStatus.MISSING,
        severity=rule.severity_if_missing,
        rationale=extraction.reasoning,
        suggestion_text=suggestion.text if suggestion else None,
        suggestion_explanation=suggestion.explanation if suggestion else None,
        **base,
    )
