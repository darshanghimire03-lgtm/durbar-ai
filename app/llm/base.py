from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUS or "tool_use_failed" in str(self)


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]
    api_id: str | None = None


@dataclass
class ToolResponse:
    id: str
    name: str
    response: dict[str, Any]
    api_id: str | None = None


@dataclass
class StreamEvent:
    text: str = ""
    calls: list[ToolCall] | None = None


class ChatSession(ABC):
    @abstractmethod
    def stream(self) -> AsyncIterator[StreamEvent]: ...

    @abstractmethod
    def add_results(self, results: list[ToolResponse]) -> None: ...