import json
from typing import Any

from app.config import get_settings
from app.llm.base import ChatSession, LLMError, StepResult, ToolCall, ToolResponse
from app.llm.registry import ModelEntry
from app.llm.transport import post_json
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

    async def step(self) -> StepResult:
        url, headers, body, timeout = self._request()
        label = f"{self.entry.provider} {self.entry.model}"
        res = await post_json(url, headers, body, timeout)

        try:
            data = res.json()
        except ValueError:
            data = None

        if res.status_code != 200 or not isinstance(data, dict) or data.get("error"):
            error = data.get("error") if isinstance(data, dict) else None
            detail = (error.get("message") if isinstance(error, dict) else error) or f"status {res.status_code}"
            status = res.status_code if res.status_code != 200 else (to_int(error.get("code") if isinstance(error, dict) else 0) or 502)
            raise LLMError(status, f"{label}: {str(detail)[:300]}")

        choices = data.get("choices") or []
        message = choices[0].get("message") if choices else None
        if not isinstance(message, dict):
            raise LLMError(502, f"{label}: empty response")

        raw_calls = message.get("tool_calls") or []
        calls = [
            ToolCall(
                id=c.get("id") or f"call_{i}",
                name=(c.get("function") or {}).get("name") or "",
                args=_parse_args((c.get("function") or {}).get("arguments")),
            )
            for i, c in enumerate(raw_calls)
        ]

        if calls:
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": [{**c, "id": c.get("id") or f"call_{i}"} for i, c in enumerate(raw_calls)],
            }
            if message.get("reasoning_details"):
                assistant["reasoning_details"] = message["reasoning_details"]
            self.messages.append(assistant)

        content = message.get("content")
        return StepResult(text=content if isinstance(content, str) else "", calls=calls)

    def add_results(self, results: list[ToolResponse]) -> None:
        for r in results:
            self.messages.append(
                {"role": "tool", "tool_call_id": r.id, "content": json.dumps(r.response, ensure_ascii=False, default=str)}
            )