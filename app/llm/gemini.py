import json
from typing import Any

from app.config import get_settings
from app.llm.base import ChatSession, LLMError, StepResult, ToolCall, ToolResponse
from app.llm.registry import ModelEntry
from app.llm.transport import post_json
from app.tools import TOOL_DEFINITIONS

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

    async def step(self) -> StepResult:
        payload = {
            "systemInstruction": {"parts": [{"text": self.system}]},
            "contents": self.contents,
            "tools": GEMINI_TOOLS,
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
        }
        headers = {"x-goog-api-key": get_settings().gemini_api_key}
        res = await post_json(f"{GEMINI_URL}/{self.entry.model}:generateContent", headers, payload, 60)

        if res.status_code != 200:
            raise LLMError(res.status_code, f"Gemini {res.status_code}: {res.text[:300]}")

        data = res.json()
        candidates = data.get("candidates") or [{}]
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []

        text = "".join(p["text"] for p in parts if isinstance(p.get("text"), str) and not p.get("thought"))
        calls = [
            ToolCall(
                id=p["functionCall"].get("id") or f"call_{i}",
                api_id=p["functionCall"].get("id"),
                name=p["functionCall"].get("name") or "",
                args=p["functionCall"].get("args") or {},
            )
            for i, p in enumerate(p for p in parts if "functionCall" in p)
        ]

        if calls and content:
            self.contents.append({"role": "model", "parts": parts})
        return StepResult(text=text, calls=calls)

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