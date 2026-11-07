import os
from datetime import timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


SERVICE_NAME = "Durbar AI"
VERSION = "0.5"

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "").strip()

CALENDAR_PATH = "calendar"
UNITS_PATH = "units"
USERS_PATH = os.getenv("USERS_PATH", "users").strip().strip("/")

CACHE_TTL_SECONDS = _int_env("CACHE_TTL_SECONDS", 60)
MAX_MESSAGE_LENGTH = 500
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# --- Ollama (optional LLM brain). Leave OLLAMA_MODEL empty to run rule-only. ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "").strip()          # e.g. https://ollama.com or http://my-server:11434
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()    # needed for Ollama cloud
OLLAMA_TIMEOUT = _int_env("OLLAMA_TIMEOUT", 60)
OLLAMA_MAX_TOKENS = _int_env("OLLAMA_MAX_TOKENS", 400)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


OLLAMA_TEMPERATURE = _float_env("OLLAMA_TEMPERATURE", 0.3)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m").strip() or None
OLLAMA_DISABLE_THINKING = os.getenv("OLLAMA_DISABLE_THINKING", "1").strip() not in ("0", "false", "no")

LLM_MAX_TOOL_ROUNDS = _int_env("LLM_MAX_TOOL_ROUNDS", 2)
LLM_TOOL_RESULT_CHARS = _int_env("LLM_TOOL_RESULT_CHARS", 3000)
LLM_HISTORY_TURNS = _int_env("LLM_HISTORY_TURNS", 6)
LLM_MAX_SESSIONS = _int_env("LLM_MAX_SESSIONS", 500)
LLM_SESSION_TTL = _int_env("LLM_SESSION_TTL", 1800)

# Per-client limit for requests that reach the LLM (they cost money/GPU time).
LLM_RATE_LIMIT = _int_env("LLM_RATE_LIMIT", 20)             # requests ...
LLM_RATE_WINDOW = _int_env("LLM_RATE_WINDOW", 60)           # ... per this many seconds

NEPAL_TZ =timezone(timedelta(hours=5, minutes=45))

KNOWLEDGE_FILE = BASE_DIR / "knowledge.json"