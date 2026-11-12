import time

from fastapi import Request

from app.config import get_settings
from app.core.errors import AppError

_WINDOW_SECONDS = 60.0
_buckets: dict[str, list[float]] = {}
_last_cleanup = 0.0


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _cleanup(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < _WINDOW_SECONDS:
        return
    _last_cleanup = now
    for key in [k for k, v in _buckets.items() if now > v[1]]:
        _buckets.pop(key, None)


async def rate_limit(request: Request) -> None:
    now = time.monotonic()
    _cleanup(now)
    key = client_ip(request)
    bucket = _buckets.get(key)
    if bucket is None or now > bucket[1]:
        bucket = [0, now + _WINDOW_SECONDS]
        _buckets[key] = bucket
    bucket[0] += 1
    if bucket[0] > get_settings().rate_limit_per_minute:
        raise AppError(429, "Too many requests. Please wait a minute.")