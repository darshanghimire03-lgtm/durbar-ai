from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class ToolContext:
    session_key: str


@dataclass
class ToolResult:
    data: dict[str, Any]
    brief: dict[str, Any] | None = None
    card: dict[str, Any] | None = None
    images: list[str] = field(default_factory=list)


Handler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


def definition(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    parameters: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        parameters["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}