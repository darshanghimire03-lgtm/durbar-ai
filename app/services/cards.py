from typing import Any

from app.utils.tables import build_table
from app.utils.text import VERIFIED_ROLES, bs_date_text, clean_url, first, norm, to_int

CARD_TYPES = ["people", "notes", "events", "national_days", "mock", "posts", "app_update", "table"]
DEFAULT_SUPPORTED = ["people", "notes"]

MAX_CARD_PEOPLE = 12
MAX_CARD_NOTES = 10
MAX_CARD_EVENTS = 15


def is_verified(role: Any) -> bool:
    return norm(role) in VERIFIED_ROLES


def people_card(people: list[dict]) -> dict | None:
    if not people:
        return None
    return {
        "type": "people",
        "people": [
            {
                "uid": str(u.get("uid") or ""),
                "name": str(u.get("fullName") or ""),
                "role": norm(u.get("role")) or "student",
                "subject": str(u.get("assignedSubject") or ""),
                "class_level": str(u.get("classLevel") or ""),
                "section": str(u.get("section") or ""),
                "photo_url": clean_url(u.get("profileImageUrl")),
                "verified": is_verified(u.get("role")),
            }
            for u in people
        ],
    }


def notes_card(subject_key: str, units: list[dict]) -> dict | None:
    groups: list[dict] = []
    total = 0
    for unit in units:
        room = MAX_CARD_NOTES - total
        if room <= 0:
            break
        notes = [{**n, "description": n["description"][:2000]} for n in unit["notes"][:room]]
        total += len(notes)
        groups.append(
            {
                "subject_key": subject_key,
                "unit_id": unit["unit_id"],
                "unit_name": unit["unit_name"],
                "notes": notes,
            }
        )
    if not groups:
        return None
    return {"type": "notes", "subject": subject_key, "groups": groups}


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


def mock_card(subject_key: str, questions: list[dict]) -> dict | None:
    if not questions:
        return None
    return {
        "type": "mock",
        "subject": subject_key,
        "questions": [
            {
                "number": i + 1,
                "question": str(q["question"]),
                "options": [str(o) for o in q["options"]],
            }
            for i, q in enumerate(questions)
        ],
    }


def events_table(events: list[dict]) -> dict | None:
    return build_table(
        "Events",
        ["No", "Type", "Title", "Subject", "Date", "Time"],
        [
            [
                i + 1,
                ev.get("event_type"),
                ev.get("title") or "",
                ev.get("subject") or subjects_text(ev),
                event_date_text(ev),
                time_text(ev),
            ]
            for i, ev in enumerate(events)
        ],
    )


def national_days_table(days: list[dict]) -> dict | None:
    return build_table(
        "National days",
        ["No", "Title", "Date", "Description"],
        [
            [i + 1, n.get("title"), bs_date_text(n.get("month"), n.get("day")), n.get("description")]
            for i, n in enumerate(days)
        ],
    )


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
    if kind == "people":
        return "Here is what I found:" if len(card["people"]) == 1 else "Here are the people I found:"
    if kind == "notes":
        return f"Here are the notes for {card['subject']}:"
    if kind == "events":
        return "Here are the events I found:"
    if kind == "national_days":
        return "Here are the national days:"
    if kind == "mock":
        return f"Here are the mock questions for {card['subject']}:"
    if kind == "posts":
        return "Here are the latest posts:"
    if kind == "app_update":
        return "Here is the latest app update:"
    if kind == "table":
        return f"Here is the table: {card['title']}" if card.get("title") else "Here is the table:"
    return "Here you go:"