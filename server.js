import "dotenv/config";
import express from "express";
import cors from "cors";
import Groq from "groq-sdk";

const PORT = process.env.PORT || 3000;
const MODEL = process.env.GROQ_MODEL || "openai/gpt-oss-120b";
const APP_API_KEY = process.env.APP_API_KEY;
const DB_URL = (process.env.FIREBASE_DATABASE_URL || "").replace(/\/+$/, "");
const DB_SECRET = process.env.FIREBASE_DB_SECRET || "";

const BS_MONTHS = [
  "Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Ashwin",
  "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
];
const EVENT_TYPES = ["exam", "test", "festival", "school_event", "emergency", "vacation"];
const STAFF_ROLES = ["professor", "captain", "moderator"];

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

const app = express();
app.use(cors());
app.use(express.json({ limit: "100kb" }));

const buckets = new Map();
function rateLimit(req, res, next) {
  const key = req.ip;
  const now = Date.now();
  const entry = buckets.get(key) || { count: 0, reset: now + 60000 };
  if (now > entry.reset) {
    entry.count = 0;
    entry.reset = now + 60000;
  }
  entry.count += 1;
  buckets.set(key, entry);
  if (entry.count > 20) {
    return res.status(429).json({ error: "Too many requests. Please wait a minute." });
  }
  next();
}

function auth(req, res, next) {
  if (APP_API_KEY && req.headers["x-api-key"] !== APP_API_KEY) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
}

const norm = (v) => String(v ?? "").toLowerCase().trim();
const has = (v, q) => norm(v).includes(norm(q));
const seg = (...parts) => parts.map((x) => encodeURIComponent(String(x))).join("/");

async function dbGet(path, shallow = false) {
  const params = new URLSearchParams();
  if (DB_SECRET) params.set("auth", DB_SECRET);
  if (shallow) params.set("shallow", "true");
  const query = params.toString();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const r = await fetch(`${DB_URL}/${path}.json${query ? `?${query}` : ""}`, {
      signal: controller.signal,
    });
    if (!r.ok) throw new Error(`RTDB ${r.status} on ${path}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

function entries(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) {
    return node.map((v, i) => [String(i), v]).filter(([, v]) => v != null);
  }
  return Object.entries(node);
}

function arr(node) {
  return entries(node).map(([, v]) => v);
}

function matchKey(keys, input) {
  if (!input) return null;
  const q = norm(input);
  return (
    keys.find((k) => norm(k) === q) ||
    keys.find((k) => norm(k).includes(q) || q.includes(norm(k))) ||
    null
  );
}

function onDay(ev, containerMonth, day) {
  if (ev.startMonth != null && ev.endMonth != null) {
    const s = Number(ev.startMonth) * 100 + Number(ev.startDay);
    const e = Number(ev.endMonth) * 100 + Number(ev.endDay);
    const t = containerMonth * 100 + day;
    return t >= s && t <= e;
  }
  return Number(ev.day) === day;
}

async function getCalendarEvents({ type, bs_year, month, day, subject, keyword } = {}) {
  const types = EVENT_TYPES.includes(type) ? [type] : EVENT_TYPES;
  let years;
  if (bs_year) {
    years = [String(bs_year)];
  } else {
    const shallow = await dbGet("calendar", true);
    years = Object.keys(shallow || {})
      .filter((k) => /^\d{4}$/.test(k))
      .sort()
      .slice(-2);
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
            type: t,
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
  found.sort((a, b) => sortKey(a) - sortKey(b));

  return {
    note: "All dates are Bikram Sambat (BS)",
    count: found.length,
    events: found.slice(0, 40),
  };
}

async function getNationalDays({ month, day, keyword } = {}) {
  const data = await dbGet("calendar/national_day");
  let list = entries(data)
    .map(([, v]) => v)
    .filter((v) => v && typeof v === "object")
    .map(({ id, photoUrl, ...rest }) => ({ ...rest, month_name: BS_MONTHS[Number(rest.month) - 1] }));
  if (month) list = list.filter((n) => Number(n.month) === Number(month));
  if (day) list = list.filter((n) => Number(n.day) === Number(day));
  if (keyword) list = list.filter((n) => has(n.title, keyword) || has(n.description, keyword));
  list.sort((a, b) => Number(a.month) * 100 + Number(a.day) - (Number(b.month) * 100 + Number(b.day)));
  return { note: "All dates are Bikram Sambat (BS)", count: list.length, national_days: list.slice(0, 40) };
}

async function getStudyMaterial({ subject, unit_name, keyword } = {}) {
  const shallow = await dbGet("units", true);
  const subjects = Object.keys(shallow || {});
  if (!subject) return { subjects };
  const key = matchKey(subjects, subject);
  if (!key) return { error: "Subject not found", subjects };

  const data = await dbGet(seg("units", key));
  let units = entries(data)
    .map(([, u]) => u)
    .filter((u) => u && typeof u === "object");
  if (unit_name) units = units.filter((u) => has(u.name, unit_name));

  const result = units.slice(0, 20).map((u) => {
    let notes = arr(u.notes).filter((n) => n && typeof n === "object");
    if (keyword) notes = notes.filter((n) => has(n.title, keyword) || has(n.description, keyword));
    return {
      unit: u.name,
      notes: notes.slice(0, 10).map((n) => ({
        title: n.title,
        description: n.description,
        pdfs: arr(n.pdfs).map((p) => ({ name: p.name, url: p.url })),
        youtube: arr(n.youtubeLinks).map((y) => y.url),
        photo_count: arr(n.photos).length,
      })),
    };
  });

  return { subject: key, count: result.length, units: result };
}

async function getMockQuestions({ subject, count } = {}) {
  const shallow = await dbGet("mocks", true);
  const subjects = Object.keys(shallow || {});
  if (!subject) return { subjects };
  const key = matchKey(subjects, subject);
  if (!key) return { error: "Subject not found", subjects };

  const data = await dbGet(seg("mocks", key, "questions"));
  const list = arr(data).filter((q) => q && q.question && Array.isArray(q.options));
  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  const n = Math.min(Math.max(Number(count) || 5, 1), 10);
  return {
    subject: key,
    total_available: list.length,
    questions: list.slice(0, n).map((q) => ({
      question: q.question,
      options: q.options,
      answer_index: q.answerIndex,
    })),
  };
}

async function getAppUpdate() {
  const data = await dbGet("app_update");
  if (!data) return { error: "No update info available" };
  const { versionName, versionCode, downloadUrl, whatsNew, updatedAt } = data;
  return {
    versionName,
    versionCode,
    downloadUrl,
    whatsNew,
    updatedAt: updatedAt ? new Date(Number(updatedAt)).toISOString().slice(0, 10) : null,
  };
}

async function getStaff({ subject, role } = {}) {
  const data = await dbGet("users");
  let list = entries(data)
    .map(([, u]) => u)
    .filter((u) => u && typeof u === "object" && STAFF_ROLES.includes(norm(u.role)));
  if (role) list = list.filter((u) => norm(u.role) === norm(role));
  if (subject) list = list.filter((u) => has(u.assignedSubject, subject));
  return {
    count: list.length,
    staff: list.slice(0, 30).map((u) => ({
      name: u.fullName,
      role: u.role,
      subject: u.assignedSubject || null,
    })),
  };
}

const handlers = {
  get_calendar_events: getCalendarEvents,
  get_national_days: getNationalDays,
  get_study_material: getStudyMaterial,
  get_mock_questions: getMockQuestions,
  get_app_update: getAppUpdate,
  get_staff: getStaff,
};

const tools = [
  {
    type: "function",
    function: {
      name: "get_calendar_events",
      description:
        "Read the Durbar school calendar (Bikram Sambat dates). Use for exam schedules, tests, festivals, school events, emergencies and vacations. For exam questions use type exam.",
      parameters: {
        type: "object",
        properties: {
          type: { type: "string", enum: EVENT_TYPES, description: "Event type. Omit to search all types." },
          bs_year: { type: "integer", description: "BS year, e.g. 2083. Omit to search the latest years." },
          month: { type: "integer", description: "BS month number 1-12 (1 Baisakh, 7 Kartik, 12 Chaitra)" },
          day: { type: "integer", description: "BS day of month" },
          subject: { type: "string", description: "Subject name filter for exams and tests" },
          keyword: { type: "string", description: "Keyword to match in title or description" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_national_days",
      description: "Read national days and public observances (Bikram Sambat month and day).",
      parameters: {
        type: "object",
        properties: {
          month: { type: "integer", description: "BS month number 1-12" },
          day: { type: "integer", description: "BS day of month" },
          keyword: { type: "string", description: "Keyword to match in title or description" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_study_material",
      description:
        "Read units and notes (PDFs, photos, YouTube lectures) by subject. Call without a subject to list available subjects.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Subject name, e.g. Computer Science" },
          unit_name: { type: "string", description: "Unit name filter" },
          keyword: { type: "string", description: "Keyword to match in note title or description" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_mock_questions",
      description:
        "Get random multiple choice mock test questions for a subject. Call without a subject to list available subjects.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Subject name" },
          count: { type: "integer", description: "Number of questions, 1-10, default 5" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_app_update",
      description: "Get the latest app version, what's new and the download link.",
      parameters: { type: "object", properties: {} },
    },
  },
  {
    type: "function",
    function: {
      name: "get_staff",
      description: "List professors, captains and moderators with their roles and assigned subjects.",
      parameters: {
        type: "object",
        properties: {
          subject: { type: "string", description: "Assigned subject filter" },
          role: { type: "string", enum: STAFF_ROLES, description: "Role filter" },
        },
      },
    },
  },
];

const SYSTEM_PROMPT = `You are Durbar AI, the official assistant inside the Durbar app.
Reply in the same language the user writes in. Keep answers short and easy to read on a phone.
For anything about exams, tests, festivals, events, vacations, study notes, mock questions, app updates or staff, ALWAYS call the matching tool and answer only from its result.
If a tool returns nothing, say that information is not available yet. Never invent dates, times, links or names.
The school calendar uses Bikram Sambat (BS). Months: 1 Baisakh, 2 Jestha, 3 Asar, 4 Shrawan, 5 Bhadra, 6 Ashwin, 7 Kartik, 8 Mangsir, 9 Poush, 10 Magh, 11 Falgun, 12 Chaitra.
Write dates like "Kartik 25, 2083". Format exams as: Subject - Date - Start to End.
For "upcoming", "next" or "tomorrow" questions use the BS date given below when available and only show events on or after it.
For mock questions, show each question with lettered options A-D, then list the answers at the end under "Answers".
When sharing notes, include the PDF names with their links and YouTube links.
Never share phone numbers, emails or any private user data.
For general questions unrelated to the app, answer helpfully and concisely.`;

function buildSystemMessage(body) {
  const lines = [SYSTEM_PROMPT];
  lines.push(`Today's date in AD is ${new Date().toISOString().slice(0, 10)}.`);
  const t = body?.today_bs;
  const y = Number(t?.year);
  const m = Number(t?.month);
  const d = Number(t?.day);
  if (y > 2000 && y < 2200 && m >= 1 && m <= 12 && d >= 1 && d <= 32) {
    lines.push(`Today's date in BS is ${BS_MONTHS[m - 1]} ${d}, ${y} (year ${y}, month ${m}, day ${d}).`);
  }
  const u = body?.user;
  if (u && typeof u === "object") {
    const clip = (v) => String(v ?? "").replace(/[\r\n]+/g, " ").slice(0, 60);
    const parts = [];
    if (u.fullName) parts.push(`name ${clip(u.fullName)}`);
    if (u.role) parts.push(`role ${clip(u.role)}`);
    if (u.classLevel) parts.push(`class ${clip(u.classLevel)}`);
    if (u.section) parts.push(`section ${clip(u.section)}`);
    if (parts.length) lines.push(`The current user: ${parts.join(", ")}.`);
  }
  return lines.join("\n");
}

app.get("/", (req, res) => res.json({ name: "Durbar AI", status: "ok", model: MODEL }));
app.get("/health", (req, res) => res.status(200).send("ok"));

app.post("/chat", rateLimit, auth, async (req, res) => {
  try {
    const message = String(req.body?.message ?? "").trim();
    if (!message) return res.status(400).json({ error: "message is required" });
    if (message.length > 1000) return res.status(400).json({ error: "message too long" });

    const history = Array.isArray(req.body?.history) ? req.body.history.slice(-10) : [];
    const cleanHistory = history
      .filter((m) => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
      .map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));

    const messages = [
      { role: "system", content: buildSystemMessage(req.body) },
      ...cleanHistory,
      { role: "user", content: message },
    ];

    for (let i = 0; i < 5; i++) {
      const completion = await groq.chat.completions.create({
        model: MODEL,
        messages,
        tools,
        tool_choice: "auto",
        temperature: 0.3,
        max_tokens: 1500,
        reasoning_effort: "low",
      });

      const msg = completion.choices[0].message;

      if (!msg.tool_calls || msg.tool_calls.length === 0) {
        return res.json({ reply: msg.content || "Sorry, I could not answer that." });
      }

      messages.push({
        role: "assistant",
        content: msg.content || "",
        tool_calls: msg.tool_calls,
      });

      for (const call of msg.tool_calls) {
        let result;
        try {
          const args = JSON.parse(call.function.arguments || "{}");
          const fn = handlers[call.function.name];
          result = fn ? await fn(args) : { error: "Unknown tool" };
        } catch (err) {
          console.error(err);
          result = { error: "Failed to read data" };
        }
        messages.push({
          role: "tool",
          tool_call_id: call.id,
          content: JSON.stringify(result),
        });
      }
    }

    res.json({ reply: "Sorry, I could not complete that request. Please try again." });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Something went wrong. Please try again." });
  }
});

app.listen(PORT, () => console.log(`Durbar AI running on port ${PORT}`));