from app.llm.base import ChatSession
from app.llm.gemini import GeminiSession
from app.llm.openai_compat import OpenAICompatSession
from app.llm.registry import ModelEntry


def create_session(entry: ModelEntry, system: str, history: list[dict], message: str) -> ChatSession:
    if entry.provider == "gemini":
        return GeminiSession(entry, system, history, message)
    return OpenAICompatSession(entry, system, history, message)