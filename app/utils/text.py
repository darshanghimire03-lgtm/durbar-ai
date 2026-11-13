import re
from typing import Any, Iterable
from urllib.parse import quote

BS_MONTHS = [
    "Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]
EVENT_TYPES = ["exam", "test", "festival", "school_event", "emergency", "vacation"]
ROLES = ["student", "professor", "captain", "moderator"]
VERIFIED_ROLES = ["professor", "captain", "moderator"]
TEACHER_ROLES = ["professor"]
SPECIAL_ROLES = ["professor", "captain", "moderator"]


def norm(value: Any) -> str:
    return str(value if value is not None else "").lower().strip()


def has(value: Any, query: Any) -> bool:
    return norm(query) in norm(value)


def seg(*parts: Any) -> str:
    return "/".join(quote(str(p), safe="") for p in parts)


def clip(value: Any, limit: int) -> str:
    return str(value if value is not None else "")[:limit]


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return value is True


def first(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def clean_url(value: Any) -> str:
    if isinstance(value, str) and re.match(r"^https?://", value.strip(), re.I):
        return value.strip()
    return ""


def match_key(keys: Iterable[str], query: Any) -> str | None:
    if not query:
        return None
    keys = list(keys)
    q = norm(query)
    for k in keys:
        if norm(k) == q:
            return k
    for k in keys:
        if norm(k) in q or q in norm(k):
            return k
    return None


def bs_date_text(month: Any, day: Any, year: Any = None) -> str:
    m = to_int(month)
    name = BS_MONTHS[m - 1] if 1 <= m <= 12 else ""
    if not name or not day:
        return ""
    return f"{name} {day}, {year}" if year else f"{name} {day}"