"""Durbar AI v0.2 - FastAPI entry point.

Run locally:  uvicorn main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from ai_engine import DurbarEngine
from firebase_data import FirebaseData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

data = FirebaseData()
engine = DurbarEngine(data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    data.connect()  # reads env vars; the app still starts if Firebase is missing
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


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
def root():
    return {"service": config.SERVICE_NAME, "version": config.VERSION, "status": "running"}


@app.get("/health")
def health():
    firebase_status, detail = data.check()
    result = {"status": "ok", "firebase": firebase_status}
    if detail:
        result["detail"] = detail
    return result


# Plain `def` (not async): FastAPI runs it in a worker thread, so the blocking
# Firebase read does not freeze the server.
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return {"reply": engine.answer(request.message)}
