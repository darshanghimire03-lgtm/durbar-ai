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
VERSION = "0.3"

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "").strip()

CALENDAR_PATH = "calendar"
UNITS_PATH = "units"

CACHE_TTL_SECONDS = _int_env("CACHE_TTL_SECONDS", 60)
MEMORY_TTL_SECONDS = _int_env("MEMORY_TTL_SECONDS", 1800)
MEMORY_MAX_SESSIONS = _int_env("MEMORY_MAX_SESSIONS", 2000)
MAX_MESSAGE_LENGTH = 500
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))

KNOWLEDGE_FILE = BASE_DIR / "knowledge.json"