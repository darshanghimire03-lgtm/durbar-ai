import dns from "node:dns/promises";
import net from "node:net";

const UA = "Mozilla/5.0 (compatible; DurbarAI/1.2)";
const MAX_BYTES = 1500000;
const MAX_TEXT = 6000;
const MAX_REDIRECTS = 4;

function privateV4(ip) {
  const [a, b] = ip.split(".").map(Number);
  return (
    a === 0 || a === 10 || a === 127 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    a >= 224
  );
}

function privateIp(ip) {
  if (net.isIPv4(ip)) return privateV4(ip);
  const l = ip.toLowerCase();
  if (l.startsWith("::ffff:")) {
    const t = l.slice(7);
    return net.isIPv4(t) ? privateV4(t) : true;
  }
  return (
    l === "::" || l === "::1" ||
    l.startsWith("fc") || l.startsWith("fd") ||
    l.startsWith("fe8") || l.startsWith("fe9") || l.startsWith("fea") || l.startsWith("feb")
  );
}

async function assertPublic(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    throw new Error("Invalid URL");
  }
  if (!["http:", "https:"].includes(u.protocol)) throw new Error("Only http and https links are allowed");
  const host = u.hostname.replace(/^\[|\]$/g, "");
  if (
    !host || host === "localhost" ||
    host.endsWith(".localhost") || host.endsWith(".internal") || host.endsWith(".local")
  ) {
    throw new Error("Blocked address");
  }
  if (net.isIP(host)) {
    if (privateIp(host)) throw new Error("Blocked address");
    return u;
  }
  const addrs = await dns.lookup(host, { all: true });
  if (!addrs.length || addrs.some((a) => privateIp(a.address))) throw new Error("Blocked address");
  return u;
}

async function readBody(res) {
  const type = (res.headers.get("content-type") || "").toLowerCase();
  const reader = res.body?.getReader();
  const chunks = [];
  let size = 0;
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_BYTES) {
        await reader.cancel();
        break;
      }
      chunks.push(value);
    }
  }
  return { ok: res.ok, status: res.status, type, text: Buffer.concat(chunks).toString("utf8") };
}

async function safeFetch(raw, init = {}) {
  let url = raw;
  for (let i = 0; i <= MAX_REDIRECTS; i++) {
    const u = await assertPublic(url);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const res = await fetch(u, {
        ...init,
        redirect: "manual",
        signal: controller.signal,
        headers: {
          "User-Agent": UA,
          Accept: "text/html,text/plain,application/json;q=0.8,*/*;q=0.5",
          ...(init.headers || {}),
        },
      });
      const loc = res.headers.get("location");
      if (res.status >= 300 && res.status < 400 && loc) {
        await res.body?.cancel?.();
        url = new URL(loc, u).toString();
        continue;
      }
      return await readBody(res);
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error("Too many redirects");
}

function codePoint(n) {
  try {
    return String.fromCodePoint(n);
  } catch {
    return " ";
  }
}

export function decodeEntities(s) {
  return String(s)
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => codePoint(Number(n)));
}

export function htmlToText(html) {
  return decodeEntities(
    String(html)
      .replace(/<(script|style|noscript|svg|iframe|nav|footer|header|form)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<!--[\s\S]*?-->/g, " ")
      .replace(/<\/(p|div|li|h[1-6]|tr|section|article)>|<br\s*\/?>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
  )
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n")
    .trim();
}

const strip = (s) => decodeEntities(String(s).replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim();

export function parseDuck(html, limit) {
  const re =
    /<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)<\/a>/g;
  const out = [];
  let m;
  while ((m = re.exec(html)) && out.length < limit) {
    let href = decodeEntities(m[1]);
    try {
      const u = new URL(href.startsWith("//") ? `https:${href}` : href, "https://duckduckgo.com");
      const real = u.searchParams.get("uddg");
      href = real || u.toString();
      if (!real && u.hostname.endsWith("duckduckgo.com")) continue;
    } catch {
      continue;
    }
    if (!/^https?:\/\//i.test(href)) continue;
    out.push({ title: strip(m[2]).slice(0, 160), url: href, snippet: strip(m[3]).slice(0, 400) });
  }
  return out;
}

async function duck(query, n) {
  const r = await safeFetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`);
  if (!r.ok) throw new Error(`DuckDuckGo ${r.status}`);
  return parseDuck(r.text, n);
}

async function wiki(query, n) {
  const url =
    "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=" +
    n + "&srsearch=" + encodeURIComponent(query);
  const r = await safeFetch(url);
  if (!r.ok) throw new Error(`Wikipedia ${r.status}`);
  const d = JSON.parse(r.text);
  return (d.query?.search || []).map((x) => ({
    title: String(x.title || ""),
    url: `https://en.wikipedia.org/wiki/${encodeURIComponent(String(x.title || "").replace(/ /g, "_"))}`,
    snippet: strip(x.snippet || "").slice(0, 400),
  }));
}

export async function searchWeb(query, limit) {
  const n = Math.min(Math.max(Number(limit) || 5, 1), 8);
  try {
    const results = await duck(query, n);
    if (results.length) return { source: "duckduckgo", results };
  } catch (err) {
    console.error(err);
  }
  try {
    const results = await wiki(query, n);
    return { source: "wikipedia", results };
  } catch (err) {
    console.error(err);
  }
  return { source: "none", results: [] };
}

export async function readPage(raw) {
  const r = await safeFetch(raw);
  if (!r.ok) throw new Error(`Page returned ${r.status}`);
  if (r.type && !/text\/|json|xml/.test(r.type)) throw new Error("Not a readable text page");
  const isHtml = /html/.test(r.type) || /<html/i.test(r.text.slice(0, 500));
  const title = isHtml ? strip((r.text.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || "") : "";
  const text = isHtml ? htmlToText(r.text) : r.text.trim();
  return { url: raw, title: title.slice(0, 160), text: text.slice(0, MAX_TEXT) };
}