import json
from typing import Any, AsyncIterator

import httpx

from app.core.http import get_client
from app.llm.base import LLMError


async def stream_sse(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> AsyncIterator[dict[str, Any]]:
    try:
        async with get_client().stream("POST", url, headers=headers, json=payload, timeout=timeout) as res:
            if res.status_code != 200:
                body = (await res.aread()).decode("utf-8", errors="replace")
                raise LLMError(res.status_code, f"Model returned {res.status_code}: {body[:300]}")
            async for line in res.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    parsed = json.loads(data)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
    except httpx.TimeoutException as exc:
        raise LLMError(504, "Model request timed out") from exc
    except httpx.TransportError as exc:
        raise LLMError(502, f"Model connection failed: {type(exc).__name__}") from exc