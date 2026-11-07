import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from ai_engine import DurbarEngine
from firebase_data import FirebaseData
from memory import Memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

data = FirebaseData()
memory = Memory()
engine = DurbarEngine(data, memory=memory)


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
    session_id: str = Field(default="", max_length=64)


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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return {"reply": engine.answer(request.message, request.session_id)}