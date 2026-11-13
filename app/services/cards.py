from typing import Any

from app.utils.text import VERIFIED_ROLES, bs_date_text, clean_url, first, norm, to_int

CARD_TYPES = ["events", "national_days", "posts", "app_update"]
DEFAULT_SUPPORTED: list[str] = []

MAX_CARD_EVENTS = 15


def is_verified(role: Any) -> bool:
    return norm(role) in VERIFIED_ROLES


def time_text(ev: dict) -> str:
    start = first(ev.get("startTime"), ev.get("start_time"), ev.get("start"))
    end = first(ev.get("endTime"), ev.get("end_time"), ev.get("end"))
    if start and end:
        return f"{start} - {end}"
    return str(first(start, ev.get("time"), "") or "")


def event_date_text(ev: dict) -> str:
    if ev.get("startMonth") is not None and ev.get("endMonth") is not None:
        same = to_int(ev.get("startMonth")) == to_int(ev.get("endMonth")) and to_int(
            ev.get("startDay")
        ) == to_int(ev.get("endDay"))
        end = bs_date_text(ev.get("endMonth"), ev.get("endDay"), ev.get("bs_year"))
        if same:
            return end
        return f"{bs_date_text(ev.get('startMonth'), ev.get('startDay'))} - {end}"
    return bs_date_text(ev.get("month"), first(ev.get("day"), ev.get("startDay")), ev.get("bs_year"))


def subjects_text(ev: dict) -> str:
    subjects = ev.get("subjects")
    return ", ".join(str(s) for s in subjects) if isinstance(subjects, list) else ""


def events_card(events: list[dict]) -> dict | None:
    if not events:
        return None
    return {
        "type": "events",
        "calendar": "Bikram Sambat (BS)",
        "events": [
            {
                "event_type": ev.get("event_type"),
                "title": str(ev.get("title") or ev.get("subject") or ""),
                "subject": str(ev.get("subject") or subjects_text(ev) or ""),
                "description": str(ev.get("description") or "")[:400],
                "date_text": event_date_text(ev),
                "time_text": time_text(ev),
                "bs_year": ev.get("bs_year"),
                "month": ev.get("month"),
                "day": to_int(first(ev.get("day"), ev.get("startDay"))),
            }
            for ev in events[:MAX_CARD_EVENTS]
        ],
    }


def national_days_card(days: list[dict]) -> dict | None:
    if not days:
        return None
    return {
        "type": "national_days",
        "calendar": "Bikram Sambat (BS)",
        "national_days": [
            {
                "title": str(n.get("title") or ""),
                "description": str(n.get("description") or "")[:400],
                "month": to_int(n.get("month")),
                "day": to_int(n.get("day")),
                "date_text": bs_date_text(n.get("month"), n.get("day")),
            }
            for n in days[:MAX_CARD_EVENTS]
        ],
    }


def posts_card(posts: list[dict]) -> dict | None:
    if not posts:
        return None
    return {
        "type": "posts",
        "posts": [
            {**{k: v for k, v in p.items() if k != "created"}, "verified": is_verified(p.get("author_role"))}
            for p in posts
        ],
    }


def app_update_card(update: dict | None) -> dict | None:
    if not update:
        return None
    return {"type": "app_update", **update}


def intro_for(card: dict) -> str:
    kind = card.get("type")
    if kind == "events":
        return "Here are the events I found:"
    if kind == "national_days":
        return "Here are the national days:"
    if kind == "posts":
        return "Here are the latest posts:"
    if kind == "app_update":
        return "Here is the latest app update:"
    return "Here you go:"