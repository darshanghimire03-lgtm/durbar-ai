import asyncio

import httpx

_client: httpx.AsyncClient | None = None
_loop: asyncio.AbstractEventLoop | None = None


def get_client() -> httpx.AsyncClient:
    global _client, _loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _loop is not loop:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=False,
        )
        _loop = loop
    return _client


async def close_client() -> None:
    global _client, _loop
    if _client is not None and not _client.is_closed:
        try:
            await _client.aclose()
        except Exception:
            pass
    _client = None
    _loop = None