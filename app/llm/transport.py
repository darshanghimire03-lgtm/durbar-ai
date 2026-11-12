import asyncio
from typing import Any

import httpx

from app.core.http import get_client
from app.llm.base import LLMError

_TRANSIENT = {502, 503, 504}


async def post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> httpx.Response:
    last: LLMError | None = None
    for attempt in range(2):
        try:
            res = await get_client().post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.TimeoutException:
            last = LLMError(504, "Model request timed out")
        except httpx.TransportError as exc:
            last = LLMError(502, f"Model connection failed: {type(exc).__name__}")
        else:
            if res.status_code in _TRANSIENT and attempt == 0:
                last = LLMError(res.status_code, f"Model returned {res.status_code}")
            else:
                return res
        if attempt == 0:
            await asyncio.sleep(0.6)
    assert last is not None
    raise last