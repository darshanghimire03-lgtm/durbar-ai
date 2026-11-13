from typing import Any

from app.services import cards
from app.services.firebase import get_app_update, search_events, search_national_days, search_posts
from app.tools.base import ToolContext, ToolResult, definition
from app.utils.text import BS_MONTHS, EVENT_TYPES, to_int

BS_NOTE = "All dates are Bikram Sambat (BS)"

DEFINITIONS = [
    definition(
        "get_calendar_events",
        "Read the Durbar school calendar (Bikram Sambat dates). Use for exam schedules, tests, festivals, "
        "school events, emergencies and vacations. For exam questions use type exam.",
        {
            "type": {"type": "string", "enum": EVENT_TYPES, "description": "Event type. Omit to search all types."},
            "bs_year": {"type": "integer", "description": "BS year, e.g. 2083. Omit to search the latest years."},
            "month": {"type": "integer", "description": "BS month number 1-12 (1 Baisakh, 7 Kartik, 12 Chaitra)"},
            "day": {"type": "integer", "description": "BS day of month"},
            "subject": {"type": "string", "description": "Subject name filter for exams and tests"},
            "keyword": {"type": "string", "description": "Keyword to match in title or description"},
        },
    ),
    definition(
        "get_national_days",
        "Read national days and public observances (Bikram Sambat month and day).",
        {
            "month": {"type": "integer", "description": "BS month number 1-12"},
            "day": {"type": "integer", "description": "BS day of month"},
            "keyword": {"type": "string", "description": "Keyword to match in title or description"},
        },
    ),
    definition("get_app_update", "Get the latest app version, what's new and the download link."),
    definition(
        "get_posts",
        "Read the latest public posts from the Durbar app feed with author, text, date, likes and comment "
        "counts. Use for questions about posts, feed or what someone posted.",
        {
            "keyword": {"type": "string", "description": "Keyword to match in post text"},
            "author": {"type": "string", "description": "Part of the author's name"},
            "limit": {"type": "integer", "description": "Number of posts, 1-10, default 5"},
        },
    ),
]


async def get_calendar_events(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    events = await search_events(
        type=args.get("type"),
        bs_year=args.get("bs_year"),
        month=args.get("month"),
        day=args.get("day"),
        subject=args.get("subject"),
        keyword=args.get("keyword"),
    )
    return ToolResult(
        data={"note": BS_NOTE, "count": len(events), "events": events[:40]},
        brief={"note": BS_NOTE, "count": len(events)},
        card=cards.events_card(events),
    )


async def get_national_days(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    days = await search_national_days(args.get("month"), args.get("day"), args.get("keyword"))
    shown = [
        {
            "title": n.get("title"),
            "description": n.get("description"),
            "month_name": BS_MONTHS[to_int(n.get("month")) - 1] if 1 <= to_int(n.get("month")) <= 12 else "",
            "day": n.get("day"),
        }
        for n in days[:40]
    ]
    return ToolResult(
        data={"note": BS_NOTE, "count": len(days), "national_days": shown},
        brief={"note": BS_NOTE, "count": len(days)},
        card=cards.national_days_card(days),
    )


async def get_app_update_tool(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    update = await get_app_update()
    if not update:
        return ToolResult(data={"error": "No update info available"})
    return ToolResult(
        data=update, brief={"version_name": update["version_name"]}, card=cards.app_update_card(update)
    )


async def get_posts(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    posts = await search_posts(args.get("keyword"), args.get("author"), args.get("limit"))
    return ToolResult(
        data={
            "count": len(posts),
            "posts": [
                {
                    "author": p["author"],
                    "text": p["text"],
                    "posted_on": p["posted_on"],
                    "likes": p["likes"],
                    "comments": p["comments"],
                    "has_images": len(p["image_urls"]) > 0,
                }
                for p in posts
            ],
        },
        brief={"count": len(posts)},
        card=cards.posts_card(posts),
    )


HANDLERS = {
    "get_calendar_events": get_calendar_events,
    "get_national_days": get_national_days,
    "get_app_update": get_app_update_tool,
    "get_posts": get_posts,
}