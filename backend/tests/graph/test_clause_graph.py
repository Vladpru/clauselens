import pytest

from app.graph.clause_graph import build_clause_graph
from app.ingest.normalize import normalize

TIMEOUT = TimeoutError("slow")


def run_clause(deps, clause_id, **kwargs):
    graph = build_clause_graph(deps)
    final = graph.invoke({"contract_id": "c1", "clause_id": clause_id, "verify_failures": 0}, **kwargs)
    assert len(final["findings"]) == 1
    return final["findings"][0]


def assert_quote_on_cited_page(result, pages):
    """AC-3: a shown quote is a normalized substring of the cited page."""
    if result.quote is not None:
        assert normalize(result.quote) in normalize(pages[result.page - 1])
    else:
        assert result.page is None


def tools_called(deps) -> list[str]:
    return [tool for tool, _ in deps.model.calls]


def test_found_verified_compliant_is_ok(deps, pages):
    result = run_clause(deps, "governing_law")
    assert result.status == "ok"
    assert result.quote and result.page == 2
    assert len(result.bboxes) >= 1
    assert result.suggestion_text is None
    assert result.candidates
    assert_quote_on_cited_page(result, pages)


def test_found_verified_non_compliant_is_risky_with_suggestion(deps, script, pages):
    script[("ClauseAssessment", "governing_law")] = {
        "compliant": False,
        "issues": ["law outside UK/EU"],
        "rationale": "New York law",
    }
    result = run_clause(deps, "governing_law")
    assert result.status == "risky"
    assert result.issues == ["law outside UK/EU"]
    assert result.rationale == "New York law"
    assert result.suggestion_text == "Better wording."
    assert result.page == 2
    assert_quote_on_cited_page(result, pages)


def test_not_found_absence_missing_is_missing_with_suggestion(deps, script, pages):
    script[("ClauseExtraction", "governing_law")] = {"found": False, "quote": None, "reasoning": "no"}
    result = run_clause(deps, "governing_law")
    assert result.status == "missing"
    assert result.severity == "medium"
    assert result.suggestion_text
    assert result.candidates
    assert result.quote is None
    assert_quote_on_cited_page(result, pages)


def test_not_found_absence_ok_is_ok_without_suggestion(deps, pages):
    result = run_clause(deps, "non_compete")
    assert result.status == "ok"
    assert result.quote is None
    assert result.suggestion_text is None
    assert result.candidates
    assert "ClauseSuggestion" not in tools_called(deps)
    assert_quote_on_cited_page(result, pages)


def test_verify_retry_then_success(deps, script, pages):
    invented = {"found": True, "quote": "This Agreement is governed by the laws of Atlantis forever.", "reasoning": "r"}
    real = {"found": True, "quote": "This Agreement shall be governed by the laws of the State of New York.", "reasoning": "r"}
    script[("ClauseExtraction", "governing_law")] = [invented, real]
    result = run_clause(deps, "governing_law")
    assert result.status == "ok"
    assert result.verify_failures == 1
    extract_calls = [m for tool, m in deps.model.calls if tool == "ClauseExtraction"]
    assert len(extract_calls) == 2
    assert "quote not found verbatim" in " ".join(str(x.content) for x in extract_calls[1])
    assert_quote_on_cited_page(result, pages)


def test_verify_fails_twice_is_uncertain(deps, script, pages):
    invented = {"found": True, "quote": "This Agreement is governed by the laws of Atlantis forever.", "reasoning": "r"}
    script[("ClauseExtraction", "governing_law")] = [invented, invented]
    result = run_clause(deps, "governing_law")
    assert result.status == "uncertain"
    assert result.quote is None
    assert result.verify_failures == 2
    assert tools_called(deps).count("ClauseExtraction") == 2
    assert result.candidates
    assert_quote_on_cited_page(result, pages)


def test_no_candidates_skips_extract(make_deps):
    from tests.fakes import FakeRetriever

    deps = make_deps(retriever=FakeRetriever())
    result = run_clause(deps, "governing_law")
    assert result.status == "missing"
    assert result.candidates == []
    assert "ClauseExtraction" not in tools_called(deps)


def test_llm_error_in_assess_is_uncertain(deps, script, pages):
    script[("ClauseAssessment", "governing_law")] = lambda messages: TIMEOUT
    result = run_clause(deps, "governing_law")
    assert result.status == "uncertain"
    assert "TimeoutError" in result.error
    assert result.quote is None
    assert result.severity is None
    assert_quote_on_cited_page(result, pages)


def test_llm_error_in_extract_is_uncertain(deps, script):
    script[("ClauseExtraction", "governing_law")] = lambda messages: TIMEOUT
    result = run_clause(deps, "governing_law")
    assert result.status == "uncertain"
    assert "TimeoutError" in result.error


def test_suggest_error_keeps_risky_status(deps, script):
    script[("ClauseAssessment", "governing_law")] = {"compliant": False, "issues": ["x"], "rationale": "r"}
    script[("ClauseSuggestion", "governing_law")] = lambda messages: TIMEOUT
    result = run_clause(deps, "governing_law")
    assert result.status == "risky"
    assert result.suggestion_text is None
    assert "TimeoutError" in result.error
    assert result.quote


def test_suggest_error_keeps_missing_status(deps, script):
    script[("ClauseExtraction", "governing_law")] = {"found": False, "quote": None, "reasoning": "no"}
    script[("ClauseSuggestion", "governing_law")] = lambda messages: TIMEOUT
    result = run_clause(deps, "governing_law")
    assert result.status == "missing"
    assert result.suggestion_text is None
    assert "TimeoutError" in result.error


def test_progress_events_emitted(deps):
    graph = build_clause_graph(deps)
    events = list(
        graph.stream(
            {"contract_id": "c1", "clause_id": "governing_law", "verify_failures": 0},
            stream_mode="custom",
        )
    )
    assert [e["step"] for e in events] == ["retrieve", "extract", "verify", "locate", "assess", "done"]
    assert {e["clause_id"] for e in events} == {"governing_law"}


@pytest.mark.parametrize("clause_id", ["governing_law", "termination_for_convenience", "cap_on_liability", "anti_assignment"])
def test_every_clause_quote_verifies_on_its_page(deps, pages, clause_id):
    assert_quote_on_cited_page(run_clause(deps, clause_id), pages)
