import {
  BS_MONTHS, EVENT_TYPES, norm, has, seg, matchKey, cleanUrl,
} from "../lib/helpers.js";

const DB_URL = (process.env.FIREBASE_DATABASE_URL || "").replace(/\/+$/, "");
const PEOPLE_PATH = process.env.PEOPLE_PATH || "users";
const CACHE_MS = Number(process.env.CACHE_MS ?? 20000);

const cache = new Map();

export async function dbGet(path, { shallow = false, useCache = true } = {}) {
  const url = `${DB_URL}/${path}.json${shallow ? "?shallow=true" : ""}`;
  if (useCache && CACHE_MS > 0) {
    const hit = cache.get(url);
    if (hit && Date.now() - hit.at < CACHE_MS) return hit.value;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const r = await fetch(url, { signal: controller.signal });
    if (!r.ok) throw new Error(`RTDB ${r.status} on ${path}`);
    const value = await r.json();
    if (useCache && CACHE_MS > 0) {
      cache.set(url, { value, at: Date.now() });
      if (cache.size > 200) cache.delete(cache.keys().next().value);
    }
    return value;
  } finally {
    clearTimeout(timer);
  }
}

export function entries(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) {
    return node.map((v, i) => [String(i), v]).filter(([, v]) => v != null);
  }
  return Object.entries(node);
}

export const arr = (node) => entries(node).map(([, v]) => v);

export async function listKeys(path) {
  const shallow = await dbGet(path, { shallow: true });
  return Object.keys(shallow || {});
}

/* ---------- calendar ---------- */

function onDay(ev, containerMonth, day) {
  if (ev.startMonth != null && ev.endMonth != null) {
    const s = Number(ev.startMonth) * 100 + Number(ev.startDay);
    const e = Number(ev.endMonth) * 100 + Number(ev.endDay);
    const t = containerMonth * 100 + day;
    return t >= s && t <= e;
  }
  return Number(ev.day) === day;
}

export async function searchEvents({ type, bs_year, month, day, subject, keyword } = {}) {
  const types = EVENT_TYPES.includes(type) ? [type] : EVENT_TYPES;
  let years;
  if (bs_year) {
    years = [String(bs_year)];
  } else {
    years = (await listKeys("calendar")).filter((k) => /^\d{4}$/.test(k)).sort().slice(-2);
  }
  const monthNum = month ? Number(month) : null;
  const dayNum = day ? Number(day) : null;

  const yearData = await Promise.all(
    years.map(async (y) => ({ y, d: await dbGet(seg("calendar", y)) }))
  );

  const found = [];
  for (const { y, d } of yearData) {
    for (const [m, mdata] of entries(d)) {
      const mn = Number(m);
      if (monthNum && mn !== monthNum) continue;
      if (!mdata || typeof mdata !== "object") continue;
      for (const t of types) {
        for (const [, ev] of entries(mdata[t])) {
          if (!ev || typeof ev !== "object") continue;
          if (dayNum && !onDay(ev, monthNum || mn, dayNum)) continue;
          if (subject && !(has(ev.subject, subject) || arr(ev.subjects).some((s) => has(s, subject)))) continue;
          if (keyword && !(has(ev.title, keyword) || has(ev.description, keyword))) continue;
          const { id, photoUrl, ...rest } = ev;
          found.push({
            event_type: t,
            bs_year: Number(y),
            month: mn,
            month_name: BS_MONTHS[mn - 1],
            ...rest,
          });
        }
      }
    }
  }

  const sortKey = (e) =>
    e.bs_year * 10000 + (Number(e.startMonth) || e.month) * 100 + (Number(e.day ?? e.startDay) || 0);
  return found.sort((a, b) => sortKey(a) - sortKey(b));
}

export async function searchNationalDays({ month, day, keyword } = {}) {
  const data = await dbGet("calendar/national_day");
  let list = entries(data)
    .map(([, v]) => v)
    .filter((v) => v && typeof v === "object")
    .map(({ id, photoUrl, ...rest }) => ({ ...rest, month_name: BS_MONTHS[Number(rest.month) - 1] }));
  if (month) list = list.filter((n) => Number(n.month) === Number(month));
  if (day) list = list.filter((n) => Number(n.day) === Number(day));
  if (keyword) list = list.filter((n) => has(n.title, keyword) || has(n.description, keyword));
  return list.sort(
    (a, b) => Number(a.month) * 100 + Number(a.day) - (Number(b.month) * 100 + Number(b.day))
  );
}

/* ---------- notes ---------- */

function normalizeNote(nKey, n) {
  return {
    id: String(n.id || nKey),
    title: String(n.title || ""),
    description: String(n.description || ""),
    pdfs: arr(n.pdfs)
      .filter((p) => p && cleanUrl(p.url))
      .map((p) => ({
        name: String(p.name || "document"),
        url: cleanUrl(p.url),
        size_bytes: Number(p.sizeBytes) || 0,
      })),
    photos: arr(n.photos)
      .map((p) => cleanUrl(p && typeof p === "object" ? p.url : p))
      .filter(Boolean),
    youtube: arr(n.youtubeLinks)
      .filter((y) => y && cleanUrl(y.url))
      .map((y) => ({
        url: cleanUrl(y.url),
        video_id: String(y.videoId || ""),
        video_number: Number(y.videoNumber) || 0,
      })),
  };
}

export async function searchNotes({ subject, unit_name, keyword } = {}) {
  const subjects = await listKeys("units");
  if (!subject) return { subjects };
  const key = matchKey(subjects, subject);
  if (!key) return { error: "Subject not found", subjects };

  const data = await dbGet(seg("units", key));
  let unitEntries = entries(data).filter(([, u]) => u && typeof u === "object");
  const unitNames = unitEntries.map(([, u]) => String(u.name || ""));
  if (unit_name) unitEntries = unitEntries.filter(([, u]) => has(u.name, unit_name));

  const units = [];
  for (const [uKey, u] of unitEntries.slice(0, 20)) {
    let noteEntries = entries(u.notes).filter(([, n]) => n && typeof n === "object");
    if (keyword) {
      noteEntries = noteEntries.filter(([, n]) => has(n.title, keyword) || has(n.description, keyword));
    }
    if (noteEntries.length === 0) continue;
    units.push({
      unit_id: String(u.id || uKey),
      unit_name: String(u.name || ""),
      notes: noteEntries.slice(0, 10).map(([nKey, n]) => normalizeNote(nKey, n)),
    });
  }
  return { subject_key: key, unit_names: unitNames, units };
}

/* ---------- mock tests ---------- */

export async function searchMocks({ subject, count } = {}) {
  const subjects = await listKeys("mocks");
  if (!subject) return { subjects };
  const key = matchKey(subjects, subject);
  if (!key) return { error: "Subject not found", subjects };

  const data = await dbGet(seg("mocks", key, "questions"), { useCache: false });
  const list = arr(data).filter((q) => q && q.question && Array.isArray(q.options));
  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  const n = Math.min(Math.max(Number(count) || 5, 1), 10);
  return {
    subject_key: key,
    total_available: list.length,
    questions: list.slice(0, n).map((q) => ({
      question: String(q.question),
      options: q.options.map(String),
      answer_index: Number(q.answerIndex),
    })),
  };
}

/* ---------- app update ---------- */

export async function getAppUpdate() {
  const data = await dbGet("app_update");
  if (!data) return null;
  const { versionName, versionCode, downloadUrl, whatsNew, updatedAt } = data;
  return {
    version_name: String(versionName || ""),
    version_code: Number(versionCode) || 0,
    download_url: cleanUrl(downloadUrl),
    whats_new: String(whatsNew || ""),
    updated_at: updatedAt ? new Date(Number(updatedAt)).toISOString().slice(0, 10) : "",
  };
}

/* ---------- people ---------- */

export async function loadPeople() {
  const data = await dbGet(PEOPLE_PATH);
  return entries(data)
    .map(([key, u]) => (u && typeof u === "object" ? { ...u, uid: u.uid || key } : null))
    .filter(Boolean);
}

export async function searchPeople({ role, name, subject, class_level, section } = {}) {
  let list = await loadPeople();
  if (role) list = list.filter((u) => norm(u.role) === norm(role));
  if (name) list = list.filter((u) => has(u.fullName, name));
  if (subject) list = list.filter((u) => has(u.assignedSubject, subject));
  if (class_level) list = list.filter((u) => norm(u.classLevel) === norm(class_level));
  if (section) list = list.filter((u) => norm(u.section) === norm(section));
  return list.sort((a, b) => norm(a.fullName).localeCompare(norm(b.fullName)));
}

/* ---------- posts ---------- */

export async function searchPosts({ keyword, author, limit } = {}) {
  const [postsData, people] = await Promise.all([
    dbGet("posts"),
    loadPeople().catch(() => []),
  ]);
  const byUid = new Map(people.map((p) => [p.uid, p]));

  let list = entries(postsData)
    .map(([, p]) => p)
    .filter((p) => p && typeof p === "object" && norm(p.privacy || "everyone") === "everyone")
    .map((p) => {
      const person = byUid.get(p.authorUid);
      const images = [p.imageUrl, ...arr(p.imageUrls)].map(cleanUrl).filter(Boolean);
      return {
        author: person?.fullName || "Unknown",
        author_role: norm(person?.role) || "student",
        author_photo_url: cleanUrl(person?.profileImageUrl),
        text: String(p.text || "").slice(0, 400),
        posted_on: p.createdAt ? new Date(Number(p.createdAt)).toISOString().slice(0, 10) : "",
        created: Number(p.createdAt) || 0,
        likes: Object.keys(p.likes || {}).length,
        comments: Object.keys(p.comments || {}).length,
        image_urls: [...new Set(images)].slice(0, 4),
      };
    });

  if (keyword) list = list.filter((p) => has(p.text, keyword));
  if (author) list = list.filter((p) => has(p.author, author));
  list.sort((a, b) => b.created - a.created);
  const n = Math.min(Math.max(Number(limit) || 5, 1), 10);
  return list.slice(0, n);
}