"""Read-only access to Firebase Realtime Database through its public REST API.

No Admin SDK and no service-account key are needed. The database rules decide
what can be read: make only `calendar` and `units` publicly readable (see README).

This module only performs HTTP GET requests. It never writes, updates or deletes,
and it only reads the two paths listed in config.py.
"""
import json
import logging
import time
import urllib.error
import urllib.request

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
        self.status = "not_configured"  # not_configured | configured
        self.error = None
        self._base = None
        self._cache = {}

    # ---- setup --------------------------------------------------------
    def connect(self) -> None:
        url = config.FIREBASE_DATABASE_URL.rstrip("/")
        if not url.startswith("https://"):
            self._base = None
            self.status = "not_configured"
            log.warning("FIREBASE_DATABASE_URL is missing or not https; data features are disabled.")
            return
        self._base = url
        self.status = "configured"
        log.info("Firebase REST reader ready.")

    @property
    def connected(self) -> bool:
        return self._base is not None

    # ---- HTTP ---------------------------------------------------------
    def _http_get(self, url: str):
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch(self, path: str, query: str = ""):
        if self._base is None:
            raise DataUnavailable("Firebase is not configured")
        url = f"{self._base}/{path}.json{query}"
        try:
            return self._http_get(url)
        except urllib.error.HTTPError as exc:
            reason = "permission_denied" if exc.code in (401, 403) else f"http_{exc.code}"
            log.error("Firebase read failed for %s: %s", path, reason)
            raise DataUnavailable(reason) from exc
        except Exception as exc:
            log.error("Firebase read failed for %s: %s", path, type(exc).__name__)
            raise DataUnavailable(type(exc).__name__) from exc

    def check(self):
        """Used by /health. Returns (status, detail)."""
        if self._base is None:
            return self.status, self.error
        try:
            self._fetch(config.CALENDAR_PATH, "?shallow=true")  # keys only: very light
            return "connected", None
        except DataUnavailable as exc:
            return "error", str(exc)

    # ---- reads (cached briefly to save bandwidth) ---------------------
    def _read(self, path: str):
        now = time.monotonic()
        hit = self._cache.get(path)
        if hit and now - hit[0] < config.CACHE_TTL_SECONDS:
            return hit[1]
        value = self._fetch(path)
        self._cache[path] = (now, value)
        return value

    def get_calendar_year(self, bs_year: int):
        """calendar/{BSyear}  ->  {month: {type: {eventId: event}}}"""
        return self._read(f"{config.CALENDAR_PATH}/{int(bs_year)}")

    def get_units(self):
        """units  ->  {subjectKey: {unitId: unit}}"""
        return self._read(config.UNITS_PATH)
