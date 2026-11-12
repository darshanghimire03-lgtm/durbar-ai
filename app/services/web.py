import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html import unescape
from urllib.parse import quote, urljoin, urlparse, parse_qs

import httpx

from app.core.http import get_client

USER_AGENT = "Mozilla/5.0 (compatible; DurbarAI/2.0)"
MAX_BYTES = 1_500_000
MAX_TEXT = 6000
MAX_REDIRECTS = 4
BLOCKED_SUFFIXES = (".localhost", ".internal", ".local")


class WebError(Exception):
    pass


@dataclass
class Fetched:
    ok: bool
    status: int
    content_type: str
    text: str


def _is_private(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (not ip.is_global) or ip.is_multicast


async def _assert_public(raw: str) -> httpx.URL:
    try:
        url = httpx.URL(raw)
    except Exception as exc:
        raise WebError("Invalid URL") from exc
    if url.scheme not in ("http", "https"):
        raise WebError("Only http and https links are allowed")

    host = (url.host or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith(BLOCKED_SUFFIXES):
        raise WebError("Blocked address")

    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        if _is_private(host):
            raise WebError("Blocked address")
        return url

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebError("Could not resolve host") from exc
    if not infos or any(_is_private(i[4][0]) for i in infos):
        raise WebError("Blocked address")
    return url


async def _safe_fetch(raw: str) -> Fetched:
    target = raw
    client = get_client()
    for _ in range(MAX_REDIRECTS + 1):
        url = await _assert_public(target)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain,application/json;q=0.8,*/*;q=0.5",
        }
        async with client.stream("GET", url, headers=headers, timeout=12) as res:
            location = res.headers.get("location")
            if 300 <= res.status_code < 400 and location:
                target = str(url.join(location))
                continue
            chunks: list[bytes] = []
            size = 0
            async for chunk in res.aiter_bytes():
                size += len(chunk)
                chunks.append(chunk)
                if size > MAX_BYTES:
                    break
            return Fetched(
                ok=res.is_success,
                status=res.status_code,
                content_type=res.headers.get("content-type", "").lower(),
                text=b"".join(chunks).decode("utf-8", errors="replace"),
            )
    raise WebError("Too many redirects")


def _strip(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", str(fragment)))).strip()


def html_to_text(html: str) -> str:
    text = re.sub(
        r"<(script|style|noscript|svg|iframe|nav|footer|header|form)\b.*?</\1>", " ", html, flags=re.I | re.S
    )
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"</(p|div|li|h[1-6]|tr|section|article)>|<br\s*/?>", "\n", text, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


_DUCK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.S,
)


def parse_duck(html: str, limit: int) -> list[dict]:
    results: list[dict] = []
    for m in _DUCK_RE.finditer(html):
        if len(results) >= limit:
            break
        href = unescape(m.group(1))
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(urljoin("https://duckduckgo.com", href))
        real = parse_qs(parsed.query).get("uddg", [""])[0]
        if real:
            href = real
        elif (parsed.hostname or "").endswith("duckduckgo.com"):
            continue
        else:
            href = parsed.geturl()
        if not re.match(r"^https?://", href, re.I):
            continue
        results.append(
            {"title": _strip(m.group(2))[:160], "url": href, "snippet": _strip(m.group(3))[:400]}
        )
    return results


async def _duckduckgo(query: str, limit: int) -> list[dict]:
    res = await _safe_fetch(f"https://html.duckduckgo.com/html/?q={quote(query)}")
    if not res.ok:
        raise WebError(f"DuckDuckGo {res.status}")
    return parse_duck(res.text, limit)


async def _wikipedia(query: str, limit: int) -> list[dict]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
        f"&srlimit={limit}&srsearch={quote(query)}"
    )
    res = await _safe_fetch(url)
    if not res.ok:
        raise WebError(f"Wikipedia {res.status}")
    items = json.loads(res.text).get("query", {}).get("search", [])
    return [
        {
            "title": str(x.get("title") or ""),
            "url": "https://en.wikipedia.org/wiki/" + quote(str(x.get("title") or "").replace(" ", "_")),
            "snippet": _strip(x.get("snippet") or "")[:400],
        }
        for x in items
    ]


async def search_web(query: str, limit: object = None) -> dict:
    try:
        n = min(max(int(float(limit)), 1), 8)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = 5
    for source, engine in (("duckduckgo", _duckduckgo), ("wikipedia", _wikipedia)):
        try:
            results = await engine(query, n)
            if results:
                return {"source": source, "results": results}
        except Exception:
            continue
    return {"source": "none", "results": []}


async def read_page(raw: str) -> dict:
    res = await _safe_fetch(raw)
    if not res.ok:
        raise WebError(f"Page returned {res.status}")
    if res.content_type and not re.search(r"text/|json|xml", res.content_type):
        raise WebError("Not a readable text page")
    is_html = "html" in res.content_type or "<html" in res.text[:500].lower()
    title = ""
    if is_html:
        m = re.search(r"<title[^>]*>(.*?)</title>", res.text, re.I | re.S)
        title = _strip(m.group(1)) if m else ""
    text = html_to_text(res.text) if is_html else res.text.strip()
    return {"url": raw, "title": title[:160], "text": text[:MAX_TEXT]}