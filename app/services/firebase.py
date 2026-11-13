import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.core.http import get_client
from app.utils.text import (
    BS_MONTHS, EVENT_TYPES, clean_url, first, has, match_key, norm, seg, to_int,
)

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_LIMIT = 200


async def db_get(path: str, *, shallow: bool = False, use_cache: bool = True) -> Any:
    settings = get_settings()
    base = settings.firebase_database_url.rstrip("/")
    if not base:
        raise RuntimeError("FIREBASE_DATABASE_URL is not configured")

    url = f"{base}/{path}.json"
    key = f"{url}?shallow={shallow}"
    ttl = settings.cache_ms / 1000
    if use_cache and ttl > 0:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]

    res = await get_client().get(url, params={"shallow": "true"} if shallow else None, timeout=10)
    if res.status_code != 200:
        raise RuntimeError(f"RTDB {res.status_code} on {path}")
    value = res.json()

    if use_cache and ttl > 0:
        _cache[key] = (time.monotonic(), value)
        if len(_cache) > _CACHE_LIMIT:
            _cache.pop(next(iter(_cache)))
    return value


def entries(node: Any) -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        return list(node.items())
    if isinstance(node, list):
        return [(str(i), v) for i, v in enumerate(node) if v is not None]
    return []


def arr(node: Any) -> list[Any]:
    return [v for _, v in entries(node)]


async def list_keys(path: str) -> list[str]:
    shallow = await db_get(path, shallow=True)
    return list(shallow.keys()) if isinstance(shallow, dict) else []


def _millis_to_date(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _on_day(ev: dict, container_month: int, day: int) -> bool:
    if ev.get("startMonth") is not None and ev.get("endMonth") is not None:
        start = to_int(ev["startMonth"]) * 100 + to_int(ev.get("startDay"))
        end = to_int(ev["endMonth"]) * 100 + to_int(ev.get("endDay"))
        target = container_month * 100 + day
        return start <= target <= end
    return to_int(ev.get("day"), -1) == day


async def search_events(
    type: str | None = None,
    bs_year: Any = None,
    month: Any = None,
    day: Any = None,
    subject: str | None = None,
    keyword: str | None = None,
) -> list[dict]:
    types = [type] if type in EVENT_TYPES else EVENT_TYPES
    if bs_year:
        years = [str(to_int(bs_year))]
    else:
        keys = await list_keys("calendar")
        years = sorted(k for k in keys if len(k) == 4 and k.isdigit())[-2:]
    month_num = to_int(month) or None
    day_num = to_int(day) or None

    year_data = await asyncio.gather(*(db_get(seg("calendar", y)) for y in years))

    found: list[dict] = []
    for year, data in zip(years, year_data):
        for m, month_data in entries(data):
            mn = to_int(m)
            if month_num and mn != month_num:
                continue
            if not isinstance(month_data, dict):
                continue
            for t in types:
                for _, ev in entries(month_data.get(t)):
                    if not isinstance(ev, dict):
                        continue
                    if day_num and not _on_day(ev, month_num or mn, day_num):
                        continue
                    if subject and not (
                        has(ev.get("subject"), subject)
                        or any(has(s, subject) for s in arr(ev.get("subjects")))
                    ):
                        continue
                    if keyword and not (has(ev.get("title"), keyword) or has(ev.get("description"), keyword)):
                        continue
                    rest = {k: v for k, v in ev.items() if k not in ("id", "photoUrl")}
                    found.append(
                        {
                            "event_type": t,
                            "bs_year": to_int(year),
                            "month": mn,
                            "month_name": BS_MONTHS[mn - 1] if 1 <= mn <= 12 else "",
                            **rest,
                        }
                    )

    def sort_key(e: dict) -> int:
        return (
            e["bs_year"] * 10000
            + (to_int(e.get("startMonth")) or e["month"]) * 100
            + to_int(first(e.get("day"), e.get("startDay")))
        )

    return sorted(found, key=sort_key)


async def search_national_days(month: Any = None, day: Any = None, keyword: str | None = None) -> list[dict]:
    data = await db_get("calendar/national_day")
    items: list[dict] = []
    for v in arr(data):
        if not isinstance(v, dict):
            continue
        rest = {k: x for k, x in v.items() if k not in ("id", "photoUrl")}
        m = to_int(rest.get("month"))
        items.append({**rest, "month_name": BS_MONTHS[m - 1] if 1 <= m <= 12 else ""})
    if month:
        items = [n for n in items if to_int(n.get("month")) == to_int(month)]
    if day:
        items = [n for n in items if to_int(n.get("day")) == to_int(day)]
    if keyword:
        items = [n for n in items if has(n.get("title"), keyword) or has(n.get("description"), keyword)]
    return sorted(items, key=lambda n: to_int(n.get("month")) * 100 + to_int(n.get("day")))


def _normalize_note(key: str, n: dict) -> dict:
    return {
        "id": str(n.get("id") or key),
        "title": str(n.get("title") or ""),
        "description": str(n.get("description") or ""),
        "pdfs": [
            {
                "name": str(p.get("name") or "document"),
                "url": clean_url(p.get("url")),
                "size_bytes": to_int(p.get("sizeBytes")),
            }
            for p in arr(n.get("pdfs"))
            if isinstance(p, dict) and clean_url(p.get("url"))
        ],
        "photos": [
            u
            for u in (clean_url(p.get("url") if isinstance(p, dict) else p) for p in arr(n.get("photos")))
            if u
        ],
        "youtube": [
            {
                "url": clean_url(y.get("url")),
                "video_id": str(y.get("videoId") or ""),
                "video_number": to_int(y.get("videoNumber")),
            }
            for y in arr(n.get("youtubeLinks"))
            if isinstance(y, dict) and clean_url(y.get("url"))
        ],
    }


async def search_notes(
    subject: str | None = None,
    unit_name: str | None = None,
    keyword: str | None = None,
    full: bool = False,
) -> dict:
    subjects = await list_keys("units")
    if not subject:
        return {"subjects": subjects}
    key = match_key(subjects, subject)
    if not key:
        return {"error": "Subject not found", "subjects": subjects}

    data = await db_get(seg("units", key))
    unit_entries = [(k, u) for k, u in entries(data) if isinstance(u, dict)]
    unit_names = [str(u.get("name") or "") for _, u in unit_entries]
    if unit_name:
        unit_entries = [(k, u) for k, u in unit_entries if has(u.get("name"), unit_name)]

    unit_cap = None if full else 20
    note_cap = None if full else 10

    units: list[dict] = []
    for u_key, u in unit_entries[:unit_cap]:
        note_entries = [(k, n) for k, n in entries(u.get("notes")) if isinstance(n, dict)]
        if keyword:
            note_entries = [
                (k, n) for k, n in note_entries if has(n.get("title"), keyword) or has(n.get("description"), keyword)
            ]
        if not note_entries:
            continue
        units.append(
            {
                "unit_id": str(u.get("id") or u_key),
                "unit_name": str(u.get("name") or ""),
                "notes": [_normalize_note(k, n) for k, n in note_entries[:note_cap]],
            }
        )
    return {"subject_key": key, "unit_names": unit_names, "units": units}


async def get_app_update() -> dict | None:
    data = await db_get("app_update")
    if not isinstance(data, dict):
        return None
    return {
        "version_name": str(data.get("versionName") or ""),
        "version_code": to_int(data.get("versionCode")),
        "download_url": clean_url(data.get("downloadUrl")),
        "whats_new": str(data.get("whatsNew") or ""),
        "updated_at": _millis_to_date(data.get("updatedAt")) if data.get("updatedAt") else "",
    }


async def load_people() -> list[dict]:
    data = await db_get(get_settings().people_path)
    return [
        {**u, "uid": u.get("uid") or key} for key, u in entries(data) if isinstance(u, dict)
    ]


async def get_person(uid: str) -> dict | None:
    if not uid or len(uid) > 128:
        return None
    data = await db_get(f"{get_settings().people_path.strip('/')}/{seg(uid)}")
    return {**data, "uid": uid} if isinstance(data, dict) else None


def _flatten(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node.strip()] if node.strip() else []
    if isinstance(node, dict):
        if node.get("active") is False:
            return []
        if "text" in node:
            return _flatten(node["text"])
        return [line for _, v in entries(node) for line in _flatten(v)]
    if isinstance(node, list):
        return [line for v in node for line in _flatten(v)]
    return []


async def get_ai_instructions() -> str:
    path = get_settings().instructions_path.strip("/")
    if not path:
        return ""
    try:
        data = await db_get(path)
    except Exception:
        return ""
    lines = _flatten(data)[:20]
    return "\n".join(f"- {line[:400]}" for line in lines)[:3000]


async def search_people(
    role: str | None = None,
    name: str | None = None,
    subject: str | None = None,
    class_level: Any = None,
    section: Any = None,
) -> list[dict]:
    people = await load_people()
    if role:
        people = [u for u in people if norm(u.get("role")) == norm(role)]
    if name:
        people = [u for u in people if has(u.get("fullName"), name)]
    if subject:
        people = [u for u in people if has(u.get("assignedSubject"), subject)]
    if class_level:
        people = [u for u in people if norm(u.get("classLevel")) == norm(class_level)]
    if section:
        people = [u for u in people if norm(u.get("section")) == norm(section)]
    return sorted(people, key=lambda u: norm(u.get("fullName")))


async def _people_or_empty() -> list[dict]:
    try:
        return await load_people()
    except Exception:
        return []


async def search_posts(keyword: str | None = None, author: str | None = None, limit: Any = None) -> list[dict]:
    posts_data, people = await asyncio.gather(db_get("posts"), _people_or_empty())
    by_uid = {p["uid"]: p for p in people}

    posts: list[dict] = []
    for p in arr(posts_data):
        if not isinstance(p, dict) or norm(p.get("privacy") or "everyone") != "everyone":
            continue
        person = by_uid.get(p.get("authorUid")) or {}
        images = [clean_url(u) for u in [p.get("imageUrl"), *arr(p.get("imageUrls"))]]
        posts.append(
            {
                "author": person.get("fullName") or "Unknown",
                "author_role": norm(person.get("role")) or "student",
                "author_photo_url": clean_url(person.get("profileImageUrl")),
                "text": str(p.get("text") or "")[:400],
                "posted_on": _millis_to_date(p.get("createdAt")) if p.get("createdAt") else "",
                "created": to_int(p.get("createdAt")),
                "likes": len(p.get("likes") or {}),
                "comments": len(p.get("comments") or {}),
                "image_urls": list(dict.fromkeys(u for u in images if u))[:4],
            }
        )

    if keyword:
        posts = [p for p in posts if has(p["text"], keyword)]
    if author:
        posts = [p for p in posts if has(p["author"], author)]
    posts.sort(key=lambda p: p["created"], reverse=True)
    n = min(max(to_int(limit, 5) or 5, 1), 10)
    return posts[:n]