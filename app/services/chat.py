import logging
import re
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
MAX_REPLY_IMAGES = 8
IMAGE_MD = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")

STATUS_TEXT = {
    "search_web": "Searching the web...",
    "read_webpage": "Reading the web page...",
    "read_pdf_notes": "Reading all the PDF notes...",
    "read_note_photos": "Reading the note photos...",
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


def scrub_images(reply: str, allowed: set[str]) -> tuple[str, list[dict]]:
    """Keep only markdown images whose URL came from a tool result. Returns the text and the kept images."""
    kept: list[dict] = []

    def swap(match: re.Match) -> str:
        url = match.group(2)
        if url not in allowed or any(k["url"] == url for k in kept) or len(kept) >= MAX_REPLY_IMAGES:
            return ""
        kept.append({"url": url, "title": match.group(1).strip()})
        return match.group(0)

    out = IMAGE_MD.sub(swap, reply)
    return re.sub(r"\n{3,}", "\n\n", out).strip(), kept


async def _run_tool(call: Any, ctx: ToolContext, supports: set[str]) -> tuple[dict, dict | None, list[str]]:
    handler = HANDLERS.get(call.name)
    if handler is None:
        return {"error": "Unknown tool"}, None, []

    result = await handler(call.args if isinstance(call.args, dict) else {}, ctx)
    shown = result.card if result.card and result.card.get("type") in supports else None
    if shown:
        return {**(result.brief or {"count": result.data.get("count")}), "cards_shown": True}, shown, result.images
    return {**result.data, "cards_shown": False}, None, result.images


async def _converse(
    entry: ModelEntry,
    system: str,
    history: list[dict],
    message: str,
    supports: set[str],
    ctx: ToolContext,
    image: dict | None = None,
) -> AsyncIterator[dict[str, Any]]:
    session = create_session(entry, system, history, message, image)
    cards: dict | None = None
    allowed_images: set[str] = set()

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
            reply, images = scrub_images(final_reply("".join(pieces), cards), allowed_images)
            body: dict[str, Any] = {"type": "done", "reply": reply or "Sorry, I could not answer that."}
            if images:
                body["images"] = images
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
                response, shown, tool_images = await _run_tool(call, ctx, supports)
                allowed_images.update(tool_images)
            except Exception:
                logger.exception("Tool %s failed", call.name)
                response, shown = {"error": "Failed to read data"}, None
            if shown:
                cards = shown
            results.append(ToolResponse(id=call.id, api_id=call.api_id, name=call.name, response=response))
        session.add_results(results)

    yield {"type": "done", "reply": GIVE_UP_REPLY}


async def answer_stream(
    entry: ModelEntry,
    system: str,
    history: list[dict],
    message: str,
    supports: set[str],
    ctx: ToolContext,
    image: dict | None = None,
) -> AsyncIterator[dict[str, Any]]:
    steps: list[str] = []
    last_error: LLMError | None = None
    for candidate in [entry, *fallback_models(entry, vision_only=image is not None)]:
        try:
            async for event in _converse(candidate, system, history, message, supports, ctx, image):
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
    entry: ModelEntry,
    system: str,
    history: list[dict],
    message: str,
    supports: set[str],
    ctx: ToolContext,
    image: dict | None = None,
) -> dict[str, Any]:
    done: dict[str, Any] | None = None
    async for event in answer_stream(entry, system, history, message, supports, ctx, image):
        if event["type"] == "done":
            done = event
    if done is None:
        raise LLMError(502, "No reply from the model")
    return {k: v for k, v in done.items() if k != "type"}