import asyncio
import io
import logging
import math
import re
from collections import Counter
from typing import Any

from pypdf import PdfReader

from app.core.http import get_client

logger = logging.getLogger(__name__)

MAX_BYTES = 12 * 1024 * 1024
MAX_PAGES = 300
CACHE_LIMIT = 80
CONCURRENCY = 5
CHUNK_CHARS = 900
CHUNK_STEP = 700
PER_PDF_LIMIT = 6
TIME_BUDGET = 38.0

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
    for index, page in enumerate(reader.pages):
        if index >= MAX_PAGES:
            break
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
    if len(_cache) > CACHE_LIMIT:
        _cache.pop(next(iter(_cache)))
    return pages


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: Any) -> list[str]:
    parts = re.split(r"[^a-z0-9\u0900-\u097f]+", str(text or "").lower())
    return [_stem(w) for w in parts if (len(w) > 2 or w.isdigit()) and w not in STOP_WORDS]


def _chunk_pages(pages: list[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for number, text in enumerate(pages, 1):
        if not text:
            continue
        start = 0
        while start < len(text):
            out.append((number, start, text[start : start + CHUNK_CHARS]))
            if start + CHUNK_CHARS >= len(text):
                break
            start += CHUNK_STEP
    return out


def _rank(docs: list[tuple[dict, list[str]]], query: str, budget: int) -> tuple[list[dict], bool]:
    words = set(tokens(query))
    rows: list[dict[str, Any]] = []
    for doc_index, (f, pages) in enumerate(docs):
        head = set(tokens(" ".join((f["name"], f["note"], f["unit"]))))
        for ordinal, (page, start, text) in enumerate(_chunk_pages(pages)):
            rows.append(
                {
                    "doc": doc_index,
                    "page": page,
                    "start": start,
                    "text": text,
                    "ordinal": ordinal,
                    "tf": Counter(tokens(text)),
                    "head": head,
                }
            )

    total = max(len(rows), 1)
    df = {w: sum(1 for r in rows if r["tf"][w]) for w in words}
    for r in rows:
        score = sum(
            (1 + math.log(r["tf"][w])) * math.log(1 + total / (1 + df[w])) for w in words if r["tf"][w]
        )
        r["score"] = score + 2.0 * len(words & r["head"])

    matched = any(r["score"] > 0 for r in rows)
    if matched:
        ordered = sorted(rows, key=lambda r: (-r["score"], r["doc"], r["page"], r["start"]))
    else:
        ordered = sorted(rows, key=lambda r: (r["ordinal"], r["doc"]))

    picked: list[dict[str, Any]] = []
    per_doc: Counter = Counter()
    used = 0
    for r in ordered:
        if used >= budget:
            break
        if per_doc[r["doc"]] >= PER_PDF_LIMIT:
            continue
        if any(
            p["doc"] == r["doc"] and p["page"] == r["page"] and abs(p["start"] - r["start"]) < CHUNK_STEP
            for p in picked
        ):
            continue
        text = r["text"][: budget - used]
        picked.append({**r, "text": text})
        per_doc[r["doc"]] += 1
        used += len(text)

    picked.sort(key=lambda r: (r["doc"], r["page"], r["start"]))
    passages = [
        {
            "subject": docs[r["doc"]][0]["subject"],
            "unit": docs[r["doc"]][0]["unit"],
            "note": docs[r["doc"]][0]["note"],
            "pdf": docs[r["doc"]][0]["name"],
            "page": r["page"],
            "text": r["text"],
        }
        for r in picked
    ]
    return passages, matched


async def crawl_pdfs(files: list[dict], query: str, budget: int) -> dict[str, Any]:
    gate = asyncio.Semaphore(CONCURRENCY)

    async def load(f: dict) -> list[str] | None:
        async with gate:
            try:
                return await read_pdf_pages(f["url"])
            except Exception:
                logger.warning("PDF read failed: %s", f["name"])
                return None

    tasks = [asyncio.create_task(load(f)) for f in files]
    done, pending = await asyncio.wait(tasks, timeout=TIME_BUDGET)
    for task in pending:
        task.cancel()

    stats = {
        "pdfs_found": len(files),
        "pdfs_read": 0,
        "pdfs_without_text": 0,
        "pdfs_failed": 0,
        "pdfs_skipped_for_time": len(pending),
    }
    docs: list[tuple[dict, list[str]]] = []
    for f, task in zip(files, tasks):
        if task not in done:
            continue
        pages = task.result()
        if pages is None:
            stats["pdfs_failed"] += 1
        elif not any(pages):
            stats["pdfs_without_text"] += 1
        else:
            stats["pdfs_read"] += 1
            docs.append((f, pages))

    passages, matched = await asyncio.to_thread(_rank, docs, query, budget)
    return {**stats, "matched": matched, "passages": passages}