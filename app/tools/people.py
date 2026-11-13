from typing import Any

from app.services.cards import MAX_CARD_PEOPLE, people_card
from app.services.firebase import search_people
from app.tools.base import ToolContext, ToolResult, definition
from app.utils.text import ROLES

DEFINITIONS = [
    definition(
        "get_people",
        "Look up people in the Durbar app: students, professors, captains and moderators. Use for questions like "
        "who is the captain, list of captains, professor of a subject, find a student, student list, how many "
        "students, who teaches X. The app shows profile cards for up to 12 matches.",
        {
            "role": {"type": "string", "enum": ROLES, "description": "Role filter"},
            "name": {"type": "string", "description": "Part of the person's name"},
            "subject": {"type": "string", "description": "Assigned subject (professors)"},
            "class_level": {"type": "string", "description": "Class level, e.g. 11"},
            "section": {"type": "string", "description": "Section, e.g. A or B"},
        },
    )
]


def _public(u: dict) -> dict[str, Any]:
    return {
        "name": u.get("fullName") or None,
        "role": u.get("role") or None,
        "subject": u.get("assignedSubject") or None,
        "class": u.get("classLevel") or None,
        "section": u.get("section") or None,
    }


async def get_people(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    people = await search_people(
        args.get("role"), args.get("name"), args.get("subject"), args.get("class_level"), args.get("section")
    )
    shown = people[:MAX_CARD_PEOPLE]
    brief: dict[str, Any] = {
        "count": len(people),
        "people": [f"{u.get('fullName')} - {u.get('role')}" for u in shown],
    }
    if len(people) > len(shown):
        brief["note"] = (
            f"The card shows only the first {len(shown)} of {len(people)}. Say how many matched and "
            "suggest narrowing by class, section or subject."
        )
    return ToolResult(
        data={"count": len(people), "people": [_public(u) for u in people[:40]]},
        brief=brief,
        card=people_card(people),
    )


HANDLERS = {"get_people": get_people}