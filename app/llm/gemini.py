import json
from typing import Any, AsyncIterator

from app.config import get_settings
from app.llm.base import ChatSession, LLMError, StreamEvent, ToolCall, ToolResponse
from app.llm.registry import ModelEntry
from app.llm.transport import stream_sse
from app.tools import TOOL_DEFINITIONS
from app.utils.text import to_int

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_OUTPUT_TOKENS = 4000


def to_gemini_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    if schema.get("type"):
        out["type"] = str(schema["type"]).upper()
    for key in ("description", "enum", "required"):
        if schema.get(key):
            out[key] = schema[key]
    if schema.get("items"):
        out["items"] = to_gemini_schema(schema["items"])
    if schema.get("properties"):
        out["properties"] = {k: to_gemini_schema(v) for k, v in schema["properties"].items()}
    return out


def _gemini_tools() -> list[dict]:
    declarations = []
    for tool in TOOL_DEFINITIONS:
        fn = tool["function"]
        params = fn.get("parameters") or {}
        declaration: dict[str, Any] = {"name": fn["name"], "description": fn["description"]}
        if params.get("properties"):
            declaration["parameters"] = to_gemini_schema(params)
        declarations.append(declaration)
    return [{"functionDeclarations": declarations}]


GEMINI_TOOLS = _gemini_tools()


def to_gemini_contents(history: list[dict], message: str) -> list[dict]:
    out: list[dict] = []
    for m in history:
        content = m.get("content") or ""
        if not content.strip():
            continue
        role = "model" if m["role"] == "assistant" else "user"
        if out and out[-1]["role"] == role:
            out[-1]["parts"][0]["text"] += "\n" + content
        else:
            out.append({"role": role, "parts": [{"text": content}]})
    while out and out[0]["role"] == "model":
        out.pop(0)

    if out and out[-1]["role"] == "user":
        out[-1]["parts"][0]["text"] += "\n" + message
    else:
        out.append({"role": "user", "parts": [{"text": message}]})
    return out


class GeminiSession(ChatSession):
    def __init__(self, entry: ModelEntry, system: str, history: list[dict], message: str) -> None:
        self.entry = entry
        self.system = system
        self.contents = to_gemini_contents(history, message)

    async def stream(self) -> AsyncIterator[StreamEvent]:
        payload = {
            "systemInstruction": {"parts": [{"text": self.system}]},
            "contents": self.contents,
            "tools": GEMINI_TOOLS,
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
        }
        headers = {"x-goog-api-key": get_settings().gemini_api_key}
        url = f"{GEMINI_URL}/{self.entry.model}:streamGenerateContent?alt=sse"

        all_parts: list[dict] = []
        calls: list[ToolCall] = []
        async for chunk in stream_sse(url, headers, payload, 90):
            error = chunk.get("error")
            if error:
                code = to_int(error.get("code")) if isinstance(error, dict) else 0
                detail = error.get("message") if isinstance(error, dict) else error
                raise LLMError(code or 502, f"Gemini: {str(detail)[:300]}")
            for candidate in (chunk.get("candidates") or [])[:1]:
                for part in (candidate.get("content") or {}).get("parts") or []:
                    if not isinstance(part, dict):
                        continue
                    all_parts.append(part)
                    text = part.get("text")
                    if isinstance(text, str) and text and not part.get("thought"):
                        yield StreamEvent(text=text)
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        calls.append(
                            ToolCall(
                                id=fc.get("id") or f"call_{len(calls)}",
                                api_id=fc.get("id"),
                                name=fc.get("name") or "",
                                args=fc.get("args") or {},
                            )
                        )

        if calls:
            self.contents.append({"role": "model", "parts": all_parts})
            yield StreamEvent(calls=calls)

    def add_results(self, results: list[ToolResponse]) -> None:
        self.contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": r.name,
                            **({"id": r.api_id} if r.api_id else {}),
                            "response": json.loads(json.dumps(r.response, default=str)),
                        }
                    }
                    for r in results
                ],
            }
        )