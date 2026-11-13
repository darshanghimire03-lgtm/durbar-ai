import logging
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from app.llm import create_session
from app.llm.base import LLMError, ToolResponse
from app.llm.registry import ModelEntry, fallback_models
from app.services.cards import intro_for
from app.tools import HANDLERS
from app.tools.base import ToolContext
from app.utils.humanize import StreamCleaner, clean_reply

logger = logging.getLogger(__name__)

MAX_ROUNDS = 6
MAX_REPLY_WITH_CARD = 160
GIVE_UP_REPLY = "Sorry, I could not complete that request. Please try again."

STATUS_TEXT = {
    "search_web": "Searching the web...",
    "read_webpage": "Reading the web page...",
    "read_pdf_notes": "Reading all the PDF notes...",
    "get_study_material": "Looking up study material...",
    "get_calendar_events": "Checking the school calendar...",
    "get_national_days": "Checking national days...",
    "get_people": "Looking up people...",
    "get_posts": "Checking the latest posts...",
    "get_app_update": "Checking the latest app update...",
}


def status_for(name: str, args: Any) -> str:
    data = args if isinstance(args, dict) else {}
    if name == "search_web":
        query = " ".join(str(data.get("query") or "").split())[:80]
        return f"Searching the web for {query}..." if query else STATUS_TEXT[name]
    if name == "read_webpage":
        host = urlparse(str(data.get("url") or "")).hostname
        return f"Reading {host}..." if host else STATUS_TEXT[name]
    return STATUS_TEXT.get(name, "Working on it...")


def final_reply(content: str, shown: dict | None) -> str:
    reply = clean_reply(content)
    if shown:
        too_long = (
            len(reply) > MAX_REPLY_WITH_CARD
            or "\n" in reply
            or "http://" in reply.lower()
            or "https://" in reply.lower()
        )
        if not reply or too_long:
            return intro_for(shown)
        return reply
    return reply or "Sorry, I could not answer that."


async def _run_tool(call: Any, ctx: ToolContext, supports: set[str]) -> tuple[dict, dict | None]:
    handler = HANDLERS.get(call.name)
    if handler is None:
        return {"error": "Unknown tool"}, None

    result = await handler(call.args if isinstance(call.args, dict) else {}, ctx)
    shown = result.card if result.card and result.card.get("type") in supports else None
    if shown:
        return {**(result.brief or {"count": result.data.get("count")}), "cards_shown": True}, shown
    return {**result.data, "cards_shown": False}, None


async def _converse(
    entry: ModelEntry, system: str, history: list[dict], message: str, supports: set[str], ctx: ToolContext
) -> AsyncIterator[dict[str, Any]]:
    session = create_session(entry, system, history, message)
    cards: dict | None = None

    for _ in range(MAX_ROUNDS):
        cleaner = StreamCleaner()
        pieces: list[str] = []
        calls: list[Any] = []

        async for event in session.stream():
            if event.text:
                pieces.append(event.text)
                out = cleaner.feed(event.text)
                if out:
                    yield {"type": "delta", "text": out}
            if event.calls:
                calls = event.calls

        tail = cleaner.flush()
        if tail:
            yield {"type": "delta", "text": tail}

        if not calls:
            body: dict[str, Any] = {"type": "done", "reply": final_reply("".join(pieces), cards)}
            if cards:
                body["cards"] = cards
            yield body
            return

        if "".join(pieces).strip():
            yield {"type": "reset"}

        results: list[ToolResponse] = []
        for call in calls:
            yield {"type": "status", "tool": call.name, "text": status_for(call.name, call.args)}
            try:
                response, shown = await _run_tool(call, ctx, supports)
            except Exception:
                logger.exception("Tool %s failed", call.name)
                response, shown = {"error": "Failed to read data"}, None
            if shown:
                cards = shown
            results.append(ToolResponse(id=call.id, api_id=call.api_id, name=call.name, response=response))
        session.add_results(results)

    yield {"type": "done", "reply": GIVE_UP_REPLY}


async def answer_stream(
    entry: ModelEntry, system: str, history: list[dict], message: str, supports: set[str], ctx: ToolContext
) -> AsyncIterator[dict[str, Any]]:
    steps: list[str] = []
    last_error: LLMError | None = None
    for candidate in [entry, *fallback_models(entry)]:
        try:
            async for event in _converse(candidate, system, history, message, supports, ctx):
                if event["type"] == "status":
                    steps.append(event["text"])
                elif event["type"] == "done":
                    event["model"] = candidate.id
                    event["steps"] = steps
                yield event
        except LLMError as exc:
            logger.warning("Model %s failed: %s", candidate.id, exc)
            last_error = exc
            if not exc.retryable:
                raise
            yield {"type": "reset"}
            continue
        return
    assert last_error is not None
    raise last_error


async def answer(
    entry: ModelEntry, system: str, history: list[dict], message: str, supports: set[str], ctx: ToolContext
) -> dict[str, Any]:
    done: dict[str, Any] | None = None
    async for event in answer_stream(entry, system, history, message, supports, ctx):
        if event["type"] == "done":
            done = event
    if done is None:
        raise LLMError(502, "No reply from the model")
    return {k: v for k, v in done.items() if k != "type"}