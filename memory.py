import threading
import time
from collections import OrderedDict

import config


class Memory:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = OrderedDict()

    @staticmethod
    def blank():
        return {"facts": {}, "last": {}, "lang": "en"}

    def get(self, session_id):
        key = str(session_id)[:64]
        now = time.monotonic()
        with self._lock:
            while self._sessions:
                oldest = next(iter(self._sessions))
                if now - self._sessions[oldest]["touched"] <= config.MEMORY_TTL_SECONDS:
                    break
                del self._sessions[oldest]
            session = self._sessions.get(key)
            if session is None:
                session = self.blank()
                self._sessions[key] = session
            session["touched"] = now
            self._sessions.move_to_end(key)
            while len(self._sessions) > config.MEMORY_MAX_SESSIONS:
                self._sessions.popitem(last=False)
            return session