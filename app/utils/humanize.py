import re
from typing import Any

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s*", re.M)
_BULLET = re.compile(r"^\s*[*•]\s+", re.M)
_EM_DASH = re.compile(r"\s*—\s*")
_OPENER = re.compile(
    r"^\s*(?:certainly|absolutely|of course|great question|good question|excellent question)[!.,]\s*"
    r"|^\s*as an ai(?: language model)?,?\s*"
    r"|^\s*i(?:'d| would) be happy to help[^.!?\n]*[.!]\s*",
    re.I,
)
_CLOSER = re.compile(
    r"(?:^|\n)[ \t]*(?:i hope (?:this|that) helps|hope (?:this|that) helps|let me know if (?:you|there)"
    r"|feel free to (?:ask|reach out)|if you (?:have|need) any (?:more|other|further|additional) questions)[^\n]*\s*$",
    re.I,
)
_SWAPS = [
    (re.compile(r"\butili[sz]e\b", re.I), "use"),
    (re.compile(r"\bdelve into\b", re.I), "look into"),
]


def polish(text: str, opener: bool = False) -> str:
    out = _LINK.sub(r"\1: \2", text)
    out = out.replace("**", "").replace("__", "")
    out = _HEADING.sub("", out)
    out = _BULLET.sub("- ", out)
    out = _EM_DASH.sub(", ", out)
    for pattern, replacement in _SWAPS:
        out = pattern.sub(replacement, out)
    if opener:
        match = _OPENER.match(out)
        if match:
            out = out[match.end():]
            out = out[:1].upper() + out[1:]
    return out


def clean_reply(text: Any) -> str:
    out = polish(str(text if text is not None else ""), opener=True)
    out = _CLOSER.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


class StreamCleaner:
    def __init__(self) -> None:
        self.buffer = ""
        self.first = True

    def _cut(self) -> int:
        buf = self.buffer
        cut = max(buf.rfind(" "), buf.rfind("\n")) + 1
        if cut <= 0:
            return 0
        open_at = buf.rfind("[", 0, cut)
        if open_at != -1 and cut - open_at < 200:
            inside = buf[open_at:cut]
            if "\n" not in inside and ")" not in inside:
                return open_at
        return cut

    def _emit(self, text: str) -> str:
        if not text:
            return ""
        out = polish(text, opener=self.first)
        if out.strip():
            self.first = False
        return out

    def feed(self, text: str) -> str:
        self.buffer += text
        if self.first and len(self.buffer) < 48 and "\n" not in self.buffer:
            return ""
        cut = self._cut()
        head, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return self._emit(head)

    def flush(self) -> str:
        head, self.buffer = self.buffer, ""
        return self._emit(head)