import time
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.core.http import get_client
from app.services.firebase import get_person
from app.utils.text import ROLES, SPECIAL_ROLES, TEACHER_ROLES, clip, norm

LOOKUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
TOKEN_TTL = 300
_tokens: dict[str, tuple[float, str]] = {}


@dataclass(frozen=True)
class Identity:
    uid: str = ""
    name: str = ""
    role: str = ""
    class_level: str = ""
    section: str = ""
    subject: str = ""
    verified: bool = False

    @property
    def kind(self) -> str:
        if self.role in TEACHER_ROLES:
            return "teacher"
        if self.role in ROLES:
            return "student"
        return "unknown"

    @property
    def special(self) -> bool:
        return self.verified and self.role in SPECIAL_ROLES


def _line(value: Any, limit: int) -> str:
    return " ".join(clip(value, limit).split())


def _role(value: Any) -> str:
    role = norm(value)
    return role if role in ROLES else ""


async def _token_uid(token: Any) -> str:
    key = get_settings().firebase_api_key
    if not key or not isinstance(token, str) or not token:
        return ""
    hit = _tokens.get(token)
    if hit and time.monotonic() - hit[0] < TOKEN_TTL:
        return hit[1]
    try:
        res = await get_client().post(f"{LOOKUP_URL}?key={key}", json={"idToken": token}, timeout=8)
        users = res.json().get("users") if res.status_code == 200 else None
    except Exception:
        users = None
    uid = str((users or [{}])[0].get("localId") or "")
    if uid:
        _tokens[token] = (time.monotonic(), uid)
        if len(_tokens) > 200:
            _tokens.pop(next(iter(_tokens)))
    return uid


async def resolve_identity(user: Any, id_token: Any) -> Identity:
    claimed = user if isinstance(user, dict) else {}
    if get_settings().firebase_api_key:
        uid = await _token_uid(id_token)
    else:
        uid = _line(claimed.get("uid"), 128)

    person = None
    if uid:
        try:
            person = await get_person(uid)
        except Exception:
            person = None

    if person:
        return Identity(
            uid=uid,
            name=_line(person.get("fullName"), 80),
            role=_role(person.get("role")),
            class_level=_line(person.get("classLevel"), 20),
            section=_line(person.get("section"), 20),
            subject=_line(person.get("assignedSubject"), 60),
            verified=True,
        )

    return Identity(
        name=_line(claimed.get("fullName"), 80),
        role=_role(claimed.get("role")),
        class_level=_line(claimed.get("classLevel"), 20),
        section=_line(claimed.get("section"), 20),
        subject=_line(claimed.get("assignedSubject"), 60),
    )