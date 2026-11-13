import json
from typing import Any, AsyncIterator

from app.config import get_settings
from app.llm.base import ChatSession, LLMError, StreamEvent, ToolCall, ToolResponse
from app.llm.registry import ModelEntry
from app.llm.transport import stream_sse
from app.tools import TOOL_DEFINITIONS
from app.utils.text import to_int

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class OpenAICompatSession(ChatSession):
    def __init__(self, entry: ModelEntry, system: str, history: list[dict], message: str) -> None:
        self.entry = entry
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": message},
        ]

    def _request(self) -> tuple[str, dict[str, str], dict[str, Any], float]:
        settings = get_settings()
        body: dict[str, Any] = {
            "model": self.entry.model,
            "messages": self.messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "max_tokens": 2500,
            "stream": True,
        }
        if self.entry.provider == "groq":
            body["temperature"] = 0.1
            if "gpt-oss" in self.entry.model:
                body["reasoning_effort"] = "low"
            headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
            return GROQ_URL, headers, body, 60

        body["temperature"] = 0.2
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "X-Title": "Durbar AI",
        }
        return OPENROUTER_URL, headers, body, 90

    async def stream(self) -> AsyncIterator[StreamEvent]:
        url, headers, body, timeout = self._request()
        label = f"{self.entry.provider} {self.entry.model}"

        text_parts: list[str] = []
        slots: dict[int, dict[str, str]] = {}
        reasoning: list[Any] = []

        async for chunk in stream_sse(url, headers, body, timeout):
            error = chunk.get("error")
            if error:
                detail = error.get("message") if isinstance(error, dict) else error
                code = to_int(error.get("code") if isinstance(error, dict) else 0) or 502
                raise LLMError(code, f"{label}: {str(detail)[:300]}")

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            content = delta.get("content")
            if isinstance(content, str) and content:
                text_parts.append(content)
                yield StreamEvent(text=content)

            for tc in delta.get("tool_calls") or []:
                slot = slots.setdefault(to_int(tc.get("index")), {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name") and not slot["name"]:
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]

            details = delta.get("reasoning_details")
            if isinstance(details, list):
                reasoning.extend(details)

        if slots:
            raw_calls = [
                {
                    "id": slot["id"] or f"call_{i}",
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"},
                }
                for i, slot in enumerate(slots[k] for k in sorted(slots))
            ]
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": raw_calls,
            }
            if reasoning:
                assistant["reasoning_details"] = reasoning
            self.messages.append(assistant)
            yield StreamEvent(
                calls=[
                    ToolCall(
                        id=c["id"],
                        name=c["function"]["name"],
                        args=_parse_args(c["function"]["arguments"]),
                    )
                    for c in raw_calls
                ]
            )

    def add_results(self, results: list[ToolResponse]) -> None:
        for r in results:
            self.messages.append(
                {"role": "tool", "tool_call_id": r.id, "content": json.dumps(r.response, ensure_ascii=False, default=str)}
            )