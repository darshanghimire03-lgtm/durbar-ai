import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.errors import AppError
from app.core.rate_limit import client_ip, rate_limit
from app.llm.base import LLMError
from app.llm.registry import available_models, default_model, find_model, public_model
from app.schemas import ChatRequest
from app.services.cards import CARD_TYPES, DEFAULT_SUPPORTED
from app.services.chat import answer
from app.services.prompt import build_system_message
from app.tools.base import ToolContext

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY = 8
MAX_HISTORY_CHARS = 1500


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

    ctx = ToolContext(session_key=str(body.session_id or client_ip(request))[:100])
    system = build_system_message(body.today_bs, body.user)

    try:
        result = await answer(
            entry, system, _clean_history(body.history), message, _supported_cards(body.cards_supported), ctx
        )
    except LLMError as exc:
        logger.error("LLM failure: %s", exc)
        if exc.status == 429:
            raise AppError(429, "This model is busy right now. Please try another model.") from exc
        raise AppError(500, "Something went wrong. Please try again.") from exc

    return JSONResponse(result)