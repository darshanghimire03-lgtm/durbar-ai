from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    provider: str
    model: str
    description: str


def all_models() -> list[ModelEntry]:
    return [
        ModelEntry("groq-gpt-oss-120b", "Groq GPT-OSS 120B", "groq", get_settings().groq_model,
                   "Fast open model running on Groq"),
        ModelEntry("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "gemini",
                   "gemini-3.5-flash-lite", "Fastest and cheapest Gemini 3.5"),
        ModelEntry("gemini-3.6-flash", "Gemini 3.6 Flash", "gemini",
                   "gemini-3.6-flash", "Smarter Gemini for harder questions"),
        ModelEntry("or-gemma-4-26b", "Google Gemma 4 26B A4B (Free)", "openrouter",
                   "google/gemma-4-26b-a4b-it:free", "Balanced Gemma model, via OpenRouter"),
    ]


def _has_key(provider: str) -> bool:
    s = get_settings()
    return bool(
        {"groq": s.groq_api_key, "gemini": s.gemini_api_key, "openrouter": s.openrouter_api_key}.get(provider)
    )


def available_models() -> list[ModelEntry]:
    return [m for m in all_models() if _has_key(m.provider)]


def default_model() -> ModelEntry | None:
    models = available_models()
    if not models:
        return None
    return next((m for m in models if m.id == get_settings().default_model), models[0])


def find_model(model_id: str) -> ModelEntry | None:
    return next((m for m in available_models() if m.id == model_id), None)


def fallback_models(entry: ModelEntry, limit: int = 2) -> list[ModelEntry]:
    if not get_settings().enable_fallback:
        return []
    return [m for m in available_models() if m.id != entry.id and m.provider != "openrouter"][:limit]


def public_model(m: ModelEntry) -> dict:
    return {"id": m.id, "label": m.label, "provider": m.provider, "description": m.description}