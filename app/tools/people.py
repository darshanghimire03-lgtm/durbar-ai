from typing import Any

from app.services.firebase import search_people
from app.tools.base import ToolContext, ToolResult, definition
from app.utils.text import ROLES

MAX_LISTED = 40

DEFINITIONS = [
    definition(
        "get_people",
        "Look up people in the Durbar app: students, professors, captains and moderators. Use for questions like "
        "who is the captain, list of captains, professor of a subject, find a student, student list, how many "
        "students, who teaches X.",
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
    data: dict[str, Any] = {"count": len(people), "people": [_public(u) for u in people[:MAX_LISTED]]}
    if len(people) > MAX_LISTED:
        data["note"] = (
            f"Only the first {MAX_LISTED} of {len(people)} are listed. Say how many matched and "
            "suggest narrowing by class, section or subject."
        )
    return ToolResult(data=data)


HANDLERS = {"get_people": get_people}