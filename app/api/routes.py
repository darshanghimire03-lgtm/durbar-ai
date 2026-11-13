import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from app.core.errors import AppError
from app.core.rate_limit import client_ip, rate_limit
from app.llm.base import LLMError
from app.llm.registry import ModelEntry, available_models, default_model, find_model, public_model
from app.schemas import ChatRequest
from app.services.cards import CARD_TYPES, DEFAULT_SUPPORTED
from app.services.chat import answer, answer_stream
from app.services.firebase import get_ai_instructions
from app.services.guard import MOCK_REPLY, is_mock_request
from app.services.identity import Identity, resolve_identity
from app.services.prompt import build_system_message
from app.tools.base import ToolContext

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY = 8
MAX_HISTORY_CHARS = 1500


@dataclass
class Prepared:
    entry: ModelEntry
    system: str
    history: list[dict]
    message: str
    supports: set[str]
    ctx: ToolContext
    who: dict[str, Any]
    blocked: bool


def _supported_cards(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set(DEFAULT_SUPPORTED)
    return {t for t in raw if isinstance(t, str) and t in CARD_TYPES}


def _clean_history(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [
        {"role": m["role"], "content": m["content"][:MAX_HISTORY_CHARS]}
        for m in raw[-MAX_HISTORY:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]


def _who(identity: Identity) -> dict[str, Any]:
    return {
        "kind": identity.kind,
        "role": identity.role or None,
        "verified": identity.verified,
        "special": identity.special,
    }


def _failure(exc: LLMError) -> tuple[int, str]:
    logger.error("LLM failure: %s", exc)
    if exc.status == 429:
        return 429, "This model is busy right now. Please try another model."
    return 500, "Something went wrong. Please try again."


async def _prepare(body: ChatRequest, request: Request) -> Prepared:
    message = str(body.message or "").strip()
    if not message:
        raise AppError(400, "message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise AppError(400, "message too long")

    if body.model:
        entry = find_model(str(body.model))
        if not entry:
            raise AppError(
                400, "Unknown or unavailable model", available=[m.id for m in available_models()]
            )
    else:
        entry = default_model()
    if not entry:
        raise AppError(503, "No AI model is configured on the server.")

    blocked = is_mock_request(message)
    identity = Identity()
    system = ""
    if not blocked:
        identity = await resolve_identity(body.user, body.id_token)
        standing = await get_ai_instructions()
        system = build_system_message(body.today_bs, identity, standing)

    return Prepared(
        entry=entry,
        system=system,
        history=_clean_history(body.history),
        message=message,
        supports=_supported_cards(body.cards_supported),
        ctx=ToolContext(session_key=str(body.session_id or client_ip(request))[:100]),
        who=_who(identity),
        blocked=blocked,
    )


def _pack(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _events(prep: Prepared) -> AsyncIterator[str]:
    yield _pack({"type": "start", "model": prep.entry.id, "user": prep.who})
    if prep.blocked:
        yield _pack({"type": "delta", "text": MOCK_REPLY})
        yield _pack({"type": "done", "reply": MOCK_REPLY, "model": prep.entry.id, "steps": []})
        return
    try:
        async for event in answer_stream(
            prep.entry, prep.system, prep.history, prep.message, prep.supports, prep.ctx
        ):
            yield _pack(event)
    except LLMError as exc:
        status, message = _failure(exc)
        yield _pack({"type": "error", "status": status, "error": message})
    except Exception:
        logger.exception("Stream failed")
        yield _pack({"type": "error", "status": 500, "error": "Something went wrong. Please try again."})


@router.get("/")
async def root() -> dict:
    model = default_model()
    return {"name": "Durbar AI", "status": "ok", "default_model": model.id if model else None}


@router.get("/health")
async def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


@router.get("/cards")
async def cards() -> dict:
    return {"card_types": CARD_TYPES, "default_supported": DEFAULT_SUPPORTED}


@router.get("/models")
async def models() -> dict:
    model = default_model()
    return {"default": model.id if model else None, "models": [public_model(m) for m in available_models()]}


@router.post("/chat", dependencies=[Depends(rate_limit)])
async def chat(body: ChatRequest, request: Request) -> JSONResponse:
    prep = await _prepare(body, request)
    if prep.blocked:
        return JSONResponse(
            {"reply": MOCK_REPLY, "model": prep.entry.id, "steps": [], "user": prep.who}
        )
    try:
        result = await answer(prep.entry, prep.system, prep.history, prep.message, prep.supports, prep.ctx)
    except LLMError as exc:
        status, message = _failure(exc)
        raise AppError(status, message) from exc
    return JSONResponse({**result, "user": prep.who})


@router.post("/chat/stream", dependencies=[Depends(rate_limit)])
async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    prep = await _prepare(body, request)
    return StreamingResponse(
        _events(prep),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )