from app.tools import mock, notes, people, school, table, web
from app.tools.base import Handler

_MODULES = (school, notes, mock, people, web, table)

TOOL_DEFINITIONS: list[dict] = [d for m in _MODULES for d in m.DEFINITIONS]
HANDLERS: dict[str, Handler] = {name: fn for m in _MODULES for name, fn in m.HANDLERS.items()}