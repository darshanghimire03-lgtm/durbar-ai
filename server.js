import "dotenv/config";
import express from "express";
import cors from "cors";
import Groq from "groq-sdk";

const PORT = process.env.PORT || 3000;
const MODEL = process.env.GROQ_MODEL || "openai/gpt-oss-120b";
const APP_API_KEY = process.env.APP_API_KEY;
const DB_URL = (process.env.FIREBASE_DATABASE_URL || "").replace(/\/+$/, "");
const DB_SECRET = process.env.FIREBASE_DB_SECRET || "";

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

async function readNode(path) {
  const qs = DB_SECRET ? `?auth=${encodeURIComponent(DB_SECRET)}` : "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const r = await fetch(`${DB_URL}/${path}.json${qs}`, { signal: controller.signal });
    if (!r.ok) throw new Error(`RTDB ${r.status}`);
    const data = await r.json();
    if (!data) return [];
    return Object.entries(data)
      .filter(([, v]) => v && typeof v === "object")
      .map(([id, v]) => ({ id, ...v }));
  } finally {
    clearTimeout(timer);
  }
}

async function getExamSchedule({ class_name, subject, date } = {}) {
  let list = await readNode("exams");
  if (class_name) list = list.filter((e) => norm(e.class).includes(norm(class_name)));
  if (subject) list = list.filter((e) => norm(e.subject).includes(norm(subject)));
  if (date) list = list.filter((e) => norm(e.date).includes(norm(date)));
  list.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  return { count: list.length, exams: list.slice(0, 30) };
}

async function getNotices({ keyword } = {}) {
  let list = await readNode("notices");
  if (keyword) {
    list = list.filter(
      (n) => norm(n.title).includes(norm(keyword)) || norm(n.body).includes(norm(keyword))
    );
  }
  return { count: list.length, notices: list.slice(-10).reverse() };
}

async function searchInfo({ topic } = {}) {
  let list = await readNode("info");
  if (topic) {
    list = list.filter(
      (i) =>
        norm(i.title).includes(norm(topic)) ||
        norm(i.content).includes(norm(topic)) ||
        norm(i.tags).includes(norm(topic))
    );
  }
  return { count: list.length, items: list.slice(0, 10) };
}

const handlers = {
  get_exam_schedule: getExamSchedule,
  get_notices: getNotices,
  search_info: searchInfo,
};

const tools = [
  {
    type: "function",
    function: {
      name: "get_exam_schedule",
      description:
        "Fetch exam schedule from the Durbar database. Use for any question about exams, exam dates, timetable, rooms or routines.",
      parameters: {
        type: "object",
        properties: {
          class_name: { type: "string", description: "Class or grade, e.g. 10, 12, BBA" },
          subject: { type: "string", description: "Subject name, e.g. Math" },
          date: { type: "string", description: "Date or partial date, e.g. 2026-11-20" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_notices",
      description: "Fetch latest notices and announcements from the Durbar database.",
      parameters: {
        type: "object",
        properties: {
          keyword: { type: "string", description: "Optional keyword to filter notices" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "search_info",
      description:
        "Search general information stored in the Durbar database such as fees, contacts, rules, facilities and admissions.",
      parameters: {
        type: "object",
        properties: {
          topic: { type: "string", description: "Topic or keyword to search for" },
        },
      },
    },
  },
];

const SYSTEM_PROMPT = `You are Durbar AI, the official assistant inside the Durbar app.
Answer clearly and briefly in the same language the user writes in.
For exam schedules, notices or app information, ALWAYS call the matching tool and answer only from its result.
If the tool returns nothing, say the information is not available yet. Never invent dates, rooms, or data.
Format exam schedules as short lines: Subject - Date - Time - Room.
For general questions unrelated to the app, answer helpfully and concisely.`;

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
      .map((m) => ({ role: m.role, content: m.content.slice(0, 1000) }));

    const messages = [
      { role: "system", content: SYSTEM_PROMPT },
      ...cleanHistory,
      { role: "user", content: message },
    ];

    for (let i = 0; i < 4; i++) {
      const completion = await groq.chat.completions.create({
        model: MODEL,
        messages,
        tools,
        tool_choice: "auto",
        temperature: 0.3,
        max_tokens: 1200,
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