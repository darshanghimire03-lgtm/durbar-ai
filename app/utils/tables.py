from html import escape
from typing import Any

AS_TABLE = {
    "type": "boolean",
    "description": "Set true when the user asks for a table or the answer is a list of rows with several fields",
}


def build_table(title: Any = "", columns: Any = None, rows: Any = None) -> dict | None:
    raw_cols = columns if isinstance(columns, list) else []
    cols = [str(c if c is not None else "")[:60] for c in raw_cols]
    cols = [c for c in cols if c][:12]
    if not cols:
        return None

    body: list[list[str]] = []
    for row in (rows if isinstance(rows, list) else [])[:100]:
        if isinstance(row, list):
            cells = row
        elif isinstance(row, dict):
            cells = [row.get(c) for c in cols]
        else:
            cells = []
        body.append(
            [
                str(cells[i] if i < len(cells) and cells[i] is not None else "")[:300]
                for i in range(len(cols))
            ]
        )
    if not body:
        return None

    return {
        "type": "table",
        "title": str(title or "")[:120],
        "columns": cols,
        "rows": body,
    }


def table_to_html(table: dict | None) -> str:
    if not table:
        return ""
    cell = "border:1px solid #cfd4dc;padding:6px 10px;text-align:left;vertical-align:top;"
    head = "".join(
        f'<th style="{cell}background:#eef1f6;">{escape(c)}</th>' for c in table["columns"]
    )
    rows = "".join(
        "<tr>" + "".join(f'<td style="{cell}">{escape(c)}</td>' for c in r) + "</tr>"
        for r in table["rows"]
    )
    caption = (
        f'<caption style="text-align:left;font-weight:bold;padding:6px 0;">{escape(table["title"])}</caption>'
        if table["title"]
        else ""
    )
    return (
        '<div style="overflow-x:auto;"><table style="border-collapse:collapse;width:100%;font-size:14px;">'
        f"{caption}<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
    )