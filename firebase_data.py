"""Read-only access to Firebase Realtime Database (Firebase Admin SDK).

This module only ever calls `.get()`. It never writes, updates or deletes, and it
only reads the two public paths listed in config.py (calendar and units).
"""
import json
import logging
import time

import config

log = logging.getLogger("durbar.firebase")


class DataUnavailable(Exception):
    """Raised when Firebase is not configured or a read fails."""


def children(node):
    """Return (key, value) pairs of a Firebase node as strings.

    Firebase returns a node as a *list* when its keys look like 0,1,2,...
    (for example months 1-12), so both dicts and lists must be handled.
    """
    if isinstance(node, dict):
        return [(str(k), v) for k, v in node.items() if v is not None]
    if isinstance(node, list):
        return [(str(i), v) for i, v in enumerate(node) if v is not None]
    return []


class FirebaseData:
    def __init__(self):
        self.status = "not_configured"  # not_configured | configured | error
        self.error = None
        self._db = None
        self._cache = {}

    # ---- connection -------------------------------------------------
    def connect(self) -> None:
        if not config.FIREBASE_DATABASE_URL or not config.FIREBASE_SERVICE_ACCOUNT_JSON:
            self.status = "not_configured"
            log.warning("Firebase env vars are missing; data features are disabled.")
            return
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            info = json.loads(config.FIREBASE_SERVICE_ACCOUNT_JSON)
            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app(
                    credentials.Certificate(info),
                    {"databaseURL": config.FIREBASE_DATABASE_URL},
                )
            self._db = db
            self.status = "configured"
            self.error = None
            log.info("Firebase initialised.")
        except Exception as exc:  # never log the credentials themselves
            self._db = None
            self.status = "error"
            self.error = type(exc).__name__
            log.error("Firebase initialisation failed: %s", self.error)

    @property
    def connected(self) -> bool:
        return self._db is not None

    def check(self):
        """Used by /health. Returns (status, detail)."""
        if self._db is None:
            return self.status, self.error
        try:
            self._db.reference(config.CALENDAR_PATH).order_by_key().limit_to_first(1).get()
            return "connected", None
        except Exception as exc:
            return "error", type(exc).__name__

    # ---- reads (cached briefly to save Firebase quota) --------------
    def _read(self, path: str):
        if self._db is None:
            raise DataUnavailable("Firebase is not connected")
        now = time.monotonic()
        hit = self._cache.get(path)
        if hit and now - hit[0] < config.CACHE_TTL_SECONDS:
            return hit[1]
        try:
            value = self._db.reference(path).get()
        except Exception as exc:
            log.error("Firebase read failed for %s: %s", path, type(exc).__name__)
            raise DataUnavailable(str(type(exc).__name__)) from exc
        self._cache[path] = (now, value)
        return value

    def get_calendar_year(self, bs_year: int):
        """calendar/{BSyear}  ->  {month: {type: {eventId: event}}}"""
        return self._read(f"{config.CALENDAR_PATH}/{int(bs_year)}")

    def get_units(self):
        """units  ->  {subjectKey: {unitId: unit}}"""
        return self._read(config.UNITS_PATH)
