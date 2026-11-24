import dataclasses

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.review_graph import ContractUnreadable, build_review_graph, run_config

CLAUSE_IDS = [
    "governing_law",
    "termination_for_convenience",
    "cap_on_liability",
    "non_compete",
    "anti_assignment",
]
ALLOWED_STATUSES = {"ok", "risky", "missing", "uncertain"}


def invoke(deps, run_id="r1"):
    graph = build_review_graph(deps, InMemorySaver())
    state = graph.invoke(
        {"run_id": run_id, "contract_id": "c1", "clause_ids": CLAUSE_IDS},
        run_config(run_id, 2),
    )
    return graph, state


def test_returns_exactly_five_findings_one_per_clause(deps):
    saved = []
    deps = dataclasses.replace(deps, save_findings=lambda run_id, findings: saved.append((run_id, findings)))
    _, state = invoke(deps)
    findings = state["findings"]
    assert len(findings) == 5
    assert {f.clause_id for f in findings} == set(CLAUSE_IDS)
    assert {f.status for f in findings} <= ALLOWED_STATUSES
    assert len(saved) == 1
    assert saved[0][0] == "r1"
    assert {f.clause_id for f in saved[0][1]} == set(CLAUSE_IDS)
    assert state["status"] == "completed"


def test_llm_error_on_one_clause_yields_uncertain(deps, script):
    script[("ClauseExtraction", "cap_on_liability")] = lambda messages: TimeoutError("slow")
    _, state = invoke(deps)
    by_clause = {f.clause_id: f for f in state["findings"]}
    assert len(by_clause) == 5
    assert by_clause["cap_on_liability"].status == "uncertain"
    assert "TimeoutError" in by_clause["cap_on_liability"].error
    assert all(f.status != "uncertain" for cid, f in by_clause.items() if cid != "cap_on_liability")
    assert state["status"] == "completed_with_errors"


def test_missing_findings_have_candidates_and_suggestion(deps, script):
    script[("ClauseExtraction", "governing_law")] = {"found": False, "quote": None, "reasoning": "no"}
    script[("ClauseAssessment", "cap_on_liability")] = {"compliant": False, "issues": ["x"], "rationale": "r"}
    _, state = invoke(deps)
    by_clause = {f.clause_id: f for f in state["findings"]}
    assert by_clause["governing_law"].status == "missing"
    assert by_clause["cap_on_liability"].status == "risky"
    assert by_clause["non_compete"].status == "ok"
    for finding in state["findings"]:
        if finding.status == "missing":
            assert finding.candidates
            assert finding.suggestion_text
        if finding.status == "ok":
            assert finding.suggestion_text is None
        if finding.status == "risky":
            assert finding.suggestion_text


def test_unreadable_contract_raises(deps, tmp_path):
    deps = dataclasses.replace(deps, contract_dir=lambda contract_id: tmp_path / "missing")
    with pytest.raises(ContractUnreadable):
        invoke(deps)


def test_checkpoint_saved_under_run_id(deps):
    graph, _ = invoke(deps, run_id="r1")
    assert graph.get_state(run_config("r1", 2)).values["status"] == "completed"


def test_custom_stream_reaches_parent(deps):
    graph = build_review_graph(deps, InMemorySaver())
    chunks = list(
        graph.stream(
            {"run_id": "r1", "contract_id": "c1", "clause_ids": CLAUSE_IDS},
            run_config("r1", 2),
            stream_mode="custom",
            subgraphs=True,
        )
    )
    done = [payload for _, payload in chunks if payload.get("step") == "done"]
    assert sorted(e["clause_id"] for e in done) == sorted(CLAUSE_IDS)


def test_run_config_sets_thread_and_concurrency():
    assert run_config("r9", 3) == {"configurable": {"thread_id": "r9"}, "max_concurrency": 3}
