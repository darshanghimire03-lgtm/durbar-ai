import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config
from ai_engine import DurbarEngine
from firebase_data import FirebaseData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

data = FirebaseData()
engine = DurbarEngine(data)


class RateLimiter:
    """Sliding-window limiter, per client, in memory (fine for a single free-plan instance)."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 5000:  # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
            return True


llm_limiter = RateLimiter(config.LLM_RATE_LIMIT, config.LLM_RATE_WINDOW)


def _client_key(request: Request) -> str:
    # Render sits behind a proxy and puts the real client first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    data.connect()
    yield


app = FastAPI(title=config.SERVICE_NAME, version=config.VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=config.MAX_MESSAGE_LENGTH)
    # Optional: send the same id on every message of a conversation so the AI remembers context.
    session_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
def root():
    return {
        "service": config.SERVICE_NAME,
        "version": config.VERSION,
        "status": "running",
        "llm": "enabled" if engine.brain.enabled else "disabled",
    }


@app.get("/health")
def health():
    firebase_status, detail = data.check()
    result = {"status": "ok", "firebase": firebase_status}
    if detail:
        result["detail"] = detail
    llm_status, llm_detail = engine.brain.check()
    result["llm"] = llm_status
    if llm_detail:
        result["llm_detail"] = llm_detail
    return result


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, http: Request):
    key = _client_key(http)
    return {"reply": engine.answer(request.message, request.session_id, lambda: llm_limiter.allow(key))}


@app.post("/chat/stream")
def chat_stream(request: ChatRequest, http: Request):
    """Server-Sent Events: `data: {"delta": "..."}` per chunk, then `data: {"done": true}`."""
    key = _client_key(http)

    def events():
        for chunk in engine.answer_stream(request.message, request.session_id, lambda: llm_limiter.allow(key)):
            yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
