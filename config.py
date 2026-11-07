"""Central configuration for Durbar AI.

All secrets come from environment variables (set them in the Render dashboard).
For local development you may put them in a `.env` file (see .env.example);
this tiny loader reads it so we do not need an extra dependency.
"""
import os
from datetime import timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a local .env file (never overrides real env vars)."""
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
VERSION = "0.2"

# --- Firebase (secrets: never hard-code, never ship in the Android APK) ---
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "").strip()
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

# The ONLY database paths this backend ever reads (both are public school info).
CALENDAR_PATH = "calendar"
UNITS_PATH = "units"

# --- Behaviour ---
CACHE_TTL_SECONDS = _int_env("CACHE_TTL_SECONDS", 60)  # reduces Firebase reads
MAX_MESSAGE_LENGTH = 500
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# Nepal Standard Time (UTC+05:45), used to decide what "today" is.
NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))

KNOWLEDGE_FILE = BASE_DIR / "knowledge.json"
