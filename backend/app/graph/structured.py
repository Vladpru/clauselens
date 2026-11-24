from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from openrouter.errors import (
    BadGatewayResponseError,
    EdgeNetworkTimeoutResponseError,
    GatewayTimeoutResponseError,
    InternalServerResponseError,
    NoResponseError,
    ProviderOverloadedResponseError,
    RequestTimeoutResponseError,
    ServiceUnavailableResponseError,
    TooManyRequestsResponseError,
)
from pydantic import BaseModel

TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
    TooManyRequestsResponseError,
    RequestTimeoutResponseError,
    InternalServerResponseError,
    BadGatewayResponseError,
    ServiceUnavailableResponseError,
    GatewayTimeoutResponseError,
    EdgeNetworkTimeoutResponseError,
    ProviderOverloadedResponseError,
    NoResponseError,
)
TRANSIENT_ATTEMPTS = 3


class StructuredCallError(Exception):
    pass


def _parse_problem(result: dict) -> str | None:
    if result.get("parsing_error") is not None:
        return str(result["parsing_error"])
    if result.get("parsed") is None:
        return "the response contained no tool call"
    return None


def invoke_structured[T: BaseModel](
    model: BaseChatModel, schema: type[T], messages: list[BaseMessage]
) -> T:
    chain = model.with_structured_output(
        schema, method="function_calling", include_raw=True
    ).with_retry(
        stop_after_attempt=TRANSIENT_ATTEMPTS,
        wait_exponential_jitter=True,
        retry_if_exception_type=TRANSIENT_ERRORS,
    )
    try:
        result = chain.invoke(messages)
        problem = _parse_problem(result)
        if problem is not None:
            feedback = HumanMessage(
                f"Your previous tool call had a validation error: {problem}\n"
                "Call the tool again with valid arguments."
            )
            result = chain.invoke([*messages, feedback])
            problem = _parse_problem(result)
    except Exception as exc:
        raise StructuredCallError(f"{type(exc).__name__}: {exc}") from exc
    if problem is not None:
        raise StructuredCallError(f"invalid structured output after one retry: {problem}")
    return result["parsed"]
