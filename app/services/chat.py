import logging
from typing import Any

from app.llm import create_session
from app.llm.base import LLMError, ToolResponse
from app.llm.registry import ModelEntry, fallback_models
from app.services.cards import intro_for
from app.tools import HANDLERS
from app.tools.base import ToolContext
from app.utils.tables import table_to_html
from app.utils.text import clean_reply

logger = logging.getLogger(__name__)

MAX_ROUNDS = 6
MAX_REPLY_WITH_CARD = 160
GIVE_UP_REPLY = "Sorry, I could not complete that request. Please try again."


def final_reply(content: str, shown: dict | None) -> str:
    reply = clean_reply(content)
    if shown:
        too_long = len(reply) > MAX_REPLY_WITH_CARD or "\n" in reply or "http://" in reply.lower() or "https://" in reply.lower()
        if not reply or too_long:
            return intro_for(shown)
        return reply
    return reply or "Sorry, I could not answer that."


async def _run_tool(call: Any, ctx: ToolContext, supports: set[str]) -> tuple[dict, dict | None, dict | None]:
    handler = HANDLERS.get(call.name)
    if handler is None:
        return {"error": "Unknown tool"}, None, None

    result = await handler(call.args if isinstance(call.args, dict) else {}, ctx)
    table = result.table
    card = result.card
    shown_card = card if (not table and card and card.get("type") in supports) else None

    if table:
        response = {**(result.brief or {"count": result.data.get("count")}), "table_shown": True}
    elif shown_card:
        response = {**(result.brief or {"count": result.data.get("count")}), "cards_shown": True}
    else:
        response = {**result.data, "cards_shown": False}
    return response, shown_card, table


async def _converse(
    entry: ModelEntry, system: str, history: list[dict], message: str, supports: set[str], ctx: ToolContext
) -> dict[str, Any]:
    session = create_session(entry, system, history, message)
    cards: dict | None = None
    table: dict | None = None

    for _ in range(MAX_ROUNDS):
        step = await session.step()

        if not step.calls:
            body: dict[str, Any] = {"reply": final_reply(step.text, cards or table)}
            if cards:
                body["cards"] = cards
            if table:
                body["table"] = table
                body["html"] = table_to_html(table)
            return body

        results: list[ToolResponse] = []
        for call in step.calls:
            try:
                response, cards, table = await _run_tool(call, ctx, supports)
            except Exception:
                logger.exception("Tool %s failed", call.name)
                response, cards, table = {"error": "Failed to read data"}, None, None
            results.append(ToolResponse(id=call.id, api_id=call.api_id, name=call.name, response=response))
        session.add_results(results)

    return {"reply": GIVE_UP_REPLY}


async def answer(
    entry: ModelEntry, system: str, history: list[dict], message: str, supports: set[str], ctx: ToolContext
) -> dict[str, Any]:
    last_error: LLMError | None = None
    for candidate in [entry, *fallback_models(entry)]:
        try:
            body = await _converse(candidate, system, history, message, supports, ctx)
        except LLMError as exc:
            logger.warning("Model %s failed: %s", candidate.id, exc)
            last_error = exc
            if not exc.retryable:
                raise
            continue
        body["model"] = candidate.id
        return body
    assert last_error is not None
    raise last_error