import pdf from "pdf-parse/lib/pdf-parse.js";

const MAX_BYTES = 12 * 1024 * 1024;
const cache = new Map();

const STOP = new Set([
  "the", "and", "for", "with", "what", "which", "who", "how", "why", "when", "where",
  "from", "this", "that", "are", "was", "were", "does", "did", "can", "you", "tell",
  "about", "give", "explain", "please", "pdf", "note", "notes", "unit", "part",
]);

async function download(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const r = await fetch(url, { signal: controller.signal });
    if (!r.ok) throw new Error(`PDF ${r.status}`);
    const len = Number(r.headers.get("content-length") || 0);
    if (len > MAX_BYTES) throw new Error("PDF too large");
    const buf = Buffer.from(await r.arrayBuffer());
    if (buf.length > MAX_BYTES) throw new Error("PDF too large");
    return buf;
  } finally {
    clearTimeout(timer);
  }
}

export async function readPdfPages(url) {
  const hit = cache.get(url);
  if (hit) return hit;

  const buf = await download(url);
  const pages = [];

  await pdf(buf, {
    pagerender: async (pageData) => {
      const content = await pageData.getTextContent({ normalizeWhitespace: true });
      let lastY;
      let text = "";
      for (const item of content.items) {
        const y = item.transform[5];
        text += lastY === undefined || lastY === y ? item.str : "\n" + item.str;
        lastY = y;
      }
      pages.push(text);
      return text;
    },
  });

  const clean = pages.map((t) =>
    t.replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim()
  );

  cache.set(url, clean);
  if (cache.size > 20) cache.delete(cache.keys().next().value);
  return clean;
}

const words = (s) =>
  String(s || "")
    .toLowerCase()
    .split(/[^a-z0-9\u0900-\u097f]+/)
    .filter((w) => w.length > 2 && !STOP.has(w));

export function pickPages(pages, query, budget) {
  const q = words(query);
  const scored = pages
    .map((text, i) => {
      const low = text.toLowerCase();
      let score = 0;
      for (const w of q) if (low.includes(w)) score += 1;
      return { page: i + 1, text, score };
    })
    .filter((p) => p.text);

  const ranked = q.length
    ? [...scored].sort((a, b) => b.score - a.score || a.page - b.page)
    : scored;

  const out = [];
  let used = 0;
  for (const p of ranked) {
    if (used >= budget) break;
    const text = p.text.slice(0, budget - used);
    out.push({ page: p.page, text });
    used += text.length;
  }
  return out.sort((a, b) => a.page - b.page);
}