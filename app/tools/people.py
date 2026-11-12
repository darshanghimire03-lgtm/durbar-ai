from typing import Any

from app.services.cards import MAX_CARD_PEOPLE, people_card
from app.services.firebase import search_people
from app.tools.base import ToolContext, ToolResult, definition
from app.utils.tables import AS_TABLE, build_table
from app.utils.text import ROLES, truthy

DEFINITIONS = [
    definition(
        "get_people",
        "Look up people in the Durbar app: students, professors, captains and moderators. Use for questions like "
        "who is the captain, list of captains, professor of a subject, find a student, student list, how many "
        "students, who teaches X. The app shows profile cards when 12 or fewer people match, and a table with "
        "column headers when more match or as_table is true.",
        {
            "role": {"type": "string", "enum": ROLES, "description": "Role filter"},
            "name": {"type": "string", "description": "Part of the person's name"},
            "subject": {"type": "string", "description": "Assigned subject (professors)"},
            "class_level": {"type": "string", "description": "Class level, e.g. 11"},
            "section": {"type": "string", "description": "Section, e.g. A or B"},
            "as_table": AS_TABLE,
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


def _table(people: list[dict]) -> dict | None:
    return build_table(
        f"People ({len(people)})",
        ["No", "Name", "Role", "Subject", "Class", "Section"],
        [
            [i + 1, u.get("fullName"), u.get("role"), u.get("assignedSubject"), u.get("classLevel"), u.get("section")]
            for i, u in enumerate(people)
        ],
    )


async def get_people(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    people = await search_people(
        args.get("role"), args.get("name"), args.get("subject"), args.get("class_level"), args.get("section")
    )
    want_table = truthy(args.get("as_table")) or len(people) > MAX_CARD_PEOPLE
    table = _table(people) if want_table and people else None
    return ToolResult(
        data={"count": len(people), "people": [_public(u) for u in people[:40]]},
        brief={
            "count": len(people),
            "people": [f"{u.get('fullName')} - {u.get('role')}" for u in people[:MAX_CARD_PEOPLE]],
        },
        card=None if table else people_card(people),
        table=table,
    )


HANDLERS = {"get_people": get_people}