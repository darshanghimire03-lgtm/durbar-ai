from typing import Any

from app.tools.base import ToolContext, ToolResult, definition
from app.utils.tables import build_table

DEFINITIONS = [
    definition(
        "send_table",
        "Send a table with column headers and filled rows to the app. Use it whenever the answer is a list of "
        "items with several fields (comparisons, schedules, student lists, study plans, search results, "
        "definitions) or when the user asks for a table. Fill every cell.",
        {
            "title": {"type": "string", "description": "Short table title"},
            "columns": {"type": "array", "items": {"type": "string"}, "description": "Column header names"},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "Each row is an array of cell values in the same order as columns",
            },
        },
        ["columns", "rows"],
    )
]


async def send_table(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    table = build_table(args.get("title"), args.get("columns"), args.get("rows"))
    if not table:
        return ToolResult(data={"error": "columns and at least one row are required"})
    return ToolResult(data={"rows": len(table["rows"])}, brief={"rows": len(table["rows"])}, table=table)


HANDLERS = {"send_table": send_table}