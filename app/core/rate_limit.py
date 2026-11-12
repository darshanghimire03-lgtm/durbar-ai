import logging
import time

from fastapi import Request

from app.config import get_settings
from app.core.errors import AppError
from app.core.http import get_client

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_buckets: dict[str, list[float]] = {}
_last_cleanup = 0.0


def client_ip(request: Request) -> str:
    """Real client IP behind Vercel's proxy (falls back to the socket address)."""
    h = request.headers
    for name in ("x-vercel-forwarded-for", "x-real-ip"):
        value = h.get(name)
        if value:
            return value.split(",")[0].strip()
    forwarded = h.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cleanup(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < _WINDOW_SECONDS:
        return
    _last_cleanup = now
    for key in [k for k, v in _buckets.items() if now > v[1]]:
        _buckets.pop(key, None)


def _memory_count(key: str) -> int:
    now = time.monotonic()
    _cleanup(now)
    bucket = _buckets.get(key)
    if bucket is None or now > bucket[1]:
        bucket = [0, now + _WINDOW_SECONDS]
        _buckets[key] = bucket
    bucket[0] += 1
    return int(bucket[0])


async def _redis_count(key: str) -> int | None:
    settings = get_settings()
    if not settings.redis_url or not settings.redis_token:
        return None
    window = int(time.time() // _WINDOW_SECONDS)
    redis_key = f"durbar:rl:{key}:{window}"
    try:
        res = await get_client().post(
            f"{settings.redis_url}/pipeline",
            headers={"Authorization": f"Bearer {settings.redis_token}"},
            json=[["INCR", redis_key], ["EXPIRE", redis_key, _WINDOW_SECONDS * 2]],
            timeout=3,
        )
        res.raise_for_status()
        return int(res.json()[0]["result"])
    except Exception as exc:  # never block users because Redis is down
        logger.warning("Redis rate limit unavailable (%s); using in-memory", type(exc).__name__)
        return None


async def rate_limit(request: Request) -> None:
    key = client_ip(request)
    count = await _redis_count(key)
    if count is None:
        count = _memory_count(key)
    if count > get_settings().rate_limit_per_minute:
        raise AppError(429, "Too many requests. Please wait a minute.")
