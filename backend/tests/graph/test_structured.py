import time

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import ClauseExtraction
from app.graph.structured import StructuredCallError, invoke_structured
from tests.fakes import ScriptedChatModel

VALID = {"found": True, "quote": "x y z a b", "reasoning": "r"}
MESSAGES = [SystemMessage("sys"), HumanMessage("find it")]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)


def scripted(*replies):
    queue = list(replies)
    return ScriptedChatModel(responder=lambda tool, messages: queue.pop(0))


def test_returns_parsed_object():
    model = scripted(VALID)
    result = invoke_structured(model, ClauseExtraction, MESSAGES)
    assert result == ClauseExtraction(**VALID)
    assert result.found is True
    assert len(model.calls) == 1


def test_retries_once_with_validation_feedback():
    model = scripted({"found": "maybe"}, VALID)
    result = invoke_structured(model, ClauseExtraction, MESSAGES)
    assert result.found is True
    assert len(model.calls) == 2
    last_message = model.calls[1][1][-1]
    assert "validation error" in str(last_message.content).lower()
    assert "found" in str(last_message.content)


def test_second_parse_failure_raises():
    model = scripted({"found": "maybe"}, {"found": "perhaps"})
    with pytest.raises(StructuredCallError):
        invoke_structured(model, ClauseExtraction, MESSAGES)
    assert len(model.calls) == 2


def test_transient_error_is_retried():
    model = scripted(TimeoutError("slow"), VALID)
    result = invoke_structured(model, ClauseExtraction, MESSAGES)
    assert result.found is True
    assert len(model.calls) == 2


def test_persistent_transient_error_raises():
    model = scripted(TimeoutError("a"), TimeoutError("b"), TimeoutError("c"))
    with pytest.raises(StructuredCallError, match="TimeoutError"):
        invoke_structured(model, ClauseExtraction, MESSAGES)
    assert len(model.calls) == 3
