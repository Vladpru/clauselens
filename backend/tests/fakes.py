import re
from collections.abc import Callable
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, PrivateAttr

from app.ingest.chunk import Chunk
from app.ingest.index import Candidate

Responder = Callable[[str, list[BaseMessage]], dict | Exception]


class ScriptedChatModel(BaseChatModel):
    """Chat model that answers each forced tool call from a responder callable."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responder: Responder
    tool_name: str = ""
    _calls: list[tuple[str, list[BaseMessage]]] = PrivateAttr(default_factory=list)

    @property
    def calls(self) -> list[tuple[str, list[BaseMessage]]]:
        return self._calls

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> ScriptedChatModel:
        if len(tools) != 1:
            raise ValueError("ScriptedChatModel supports exactly one tool")
        name = convert_to_openai_tool(tools[0])["function"]["name"]
        return self.model_copy(update={"tool_name": name})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._calls.append((self.tool_name, list(messages)))
        reply = self.responder(self.tool_name, messages)
        if isinstance(reply, Exception):
            raise reply
        message = AIMessage(
            content="",
            tool_calls=[{"name": self.tool_name, "args": reply, "id": "call-1"}],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class FakeRetriever:
    """Retriever keyed by a substring of the query, with a default result."""

    def __init__(
        self,
        by_query: dict[str, list[Candidate]] | None = None,
        default: list[Candidate] | None = None,
    ) -> None:
        self.by_query = by_query or {}
        self.default = default or []

    def search(self, contract_id: str, query: str, k: int) -> list[Candidate]:
        for key, candidates in self.by_query.items():
            if key in query:
                return candidates[:k]
        return self.default[:k]

    def add_contract(self, contract_id: str, chunks: list[Chunk]) -> int:
        return len(chunks)


def clause_of(messages: list[BaseMessage]) -> str:
    for message in messages:
        match = re.search(r"clause_id=(\w+)", str(message.content))
        if message.type == "system" and match:
            return match.group(1)
    raise ValueError("no clause_id= marker in the system message")
