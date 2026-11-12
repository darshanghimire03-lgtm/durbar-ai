import asyncio
import io
import re

from pypdf import PdfReader

from app.core.http import get_client

MAX_BYTES = 12 * 1024 * 1024
_CACHE_LIMIT = 20
_cache: dict[str, list[str]] = {}

STOP_WORDS = {
    "the", "and", "for", "with", "what", "which", "who", "how", "why", "when", "where",
    "from", "this", "that", "are", "was", "were", "does", "did", "can", "you", "tell",
    "about", "give", "explain", "please", "pdf", "note", "notes", "unit", "part",
}


async def _download(url: str) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async with get_client().stream("GET", url, timeout=20, follow_redirects=True) as res:
        if res.status_code != 200:
            raise RuntimeError(f"PDF {res.status_code}")
        if int(res.headers.get("content-length") or 0) > MAX_BYTES:
            raise RuntimeError("PDF too large")
        async for chunk in res.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise RuntimeError("PDF too large")
            chunks.append(chunk)
    return b"".join(chunks)


def _extract(data: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt("")
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        pages.append(text.strip())
    return pages


async def read_pdf_pages(url: str) -> list[str]:
    hit = _cache.get(url)
    if hit is not None:
        return hit
    pages = await asyncio.to_thread(_extract, await _download(url))
    _cache[url] = pages
    if len(_cache) > _CACHE_LIMIT:
        _cache.pop(next(iter(_cache)))
    return pages


def _words(text: str) -> list[str]:
    parts = re.split(r"[^a-z0-9\u0900-\u097f]+", str(text or "").lower())
    return [w for w in parts if len(w) > 2 and w not in STOP_WORDS]


def pick_pages(pages: list[str], query: str, budget: int) -> list[dict]:
    words = _words(query)
    scored: list[tuple[int, int, str]] = []
    for index, text in enumerate(pages):
        if not text:
            continue
        low = text.lower()
        scored.append((sum(1 for w in words if w in low), index + 1, text))

    ranked = sorted(scored, key=lambda s: (-s[0], s[1])) if words else scored

    picked: list[dict] = []
    used = 0
    for _, page, text in ranked:
        if used >= budget:
            break
        chunk = text[: budget - used]
        picked.append({"page": page, "text": chunk})
        used += len(chunk)
    return sorted(picked, key=lambda p: p["page"])