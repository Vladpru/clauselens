import logging
import warnings

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.graph.state import (
    ClauseAssessment,
    ClauseExtraction,
    ClauseSuggestion,
    FindingResult,
)
from app.ingest.index import Candidate
from app.services import checkpoint_serde


def sample_state():
    return {
        "findings": [
            FindingResult(
                clause_id="governing_law",
                status="ok",
                playbook_rule="r",
                candidates=[Candidate(chunk_id="1-0", page=1, text="t")],
            )
        ],
        "extraction": ClauseExtraction(found=True, quote="a b c d e", reasoning="r"),
        "assessment": ClauseAssessment(compliant=True, issues=[], rationale="r"),
        "suggestion": ClauseSuggestion(text="t", explanation="e"),
    }


def roundtrip(serde, caplog):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.WARNING):
            restored = serde.loads_typed(serde.dumps_typed(sample_state()))
    messages = [str(w.message) for w in caught] + [r.getMessage() for r in caplog.records]
    return restored, [m for m in messages if "unregistered type" in m]


def test_checkpoint_serde_restores_graph_types_without_warnings(caplog):
    restored, complaints = roundtrip(checkpoint_serde(), caplog)
    assert complaints == []
    assert restored["findings"][0] == sample_state()["findings"][0]
    assert restored["extraction"] == sample_state()["extraction"]
    assert restored["findings"][0].candidates[0].page == 1


def test_default_serde_warns_about_these_types(caplog):
    _, complaints = roundtrip(JsonPlusSerializer(), caplog)
    assert complaints, "if this fails, LangGraph no longer warns and the allowlist may be unnecessary"
