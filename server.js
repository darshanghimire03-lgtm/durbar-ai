import "dotenv/config";
import express from "express";
import cors from "cors";
import Groq from "groq-sdk";
import { cleanReply } from "./lib/helpers.js";
import { CARD_TYPES, DEFAULT_SUPPORTED, introFor } from "./lib/cards.js";
import { buildSystemMessage } from "./lib/prompt.js";
import { tools } from "./tools/definitions.js";
import { handlers } from "./tools/handlers.js";

const PORT = process.env.PORT || 3000;
const MODEL = process.env.GROQ_MODEL || "openai/gpt-oss-120b";

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

const app = express();
app.set("trust proxy", 1);
app.use(cors());
app.use(express.json({ limit: "100kb" }));

const buckets = new Map();
setInterval(() => {
  const now = Date.now();
  for (const [k, v] of buckets) if (now > v.reset) buckets.delete(k);
}, 60000).unref();

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
  if (entry.count > 15) {
    return res.status(429).json({ error: "Too many requests. Please wait a minute." });
  }
  next();
}

function parseSupported(raw) {
  if (!Array.isArray(raw)) return new Set(DEFAULT_SUPPORTED);
  return new Set(raw.filter((t) => CARD_TYPES.includes(t)));
}

function finalReply(content, cards) {
  let reply = cleanReply(content);
  if (cards) {
    const tooLong = reply.length > 160 || reply.includes("\n") || /https?:\/\//i.test(reply);
    if (!reply || tooLong) reply = introFor(cards);
  } else if (!reply) {
    reply = "Sorry, I could not answer that.";
  }
  return reply;
}

app.get("/", (req, res) => res.json({ name: "Durbar AI", status: "ok", model: MODEL }));
app.get("/health", (req, res) => res.status(200).send("ok"));
app.get("/cards", (req, res) =>
  res.json({ card_types: CARD_TYPES, default_supported: DEFAULT_SUPPORTED })
);

app.post("/chat", rateLimit, async (req, res) => {
  try {
    const message = String(req.body?.message ?? "").trim();
    if (!message) return res.status(400).json({ error: "message is required" });
    if (message.length > 1000) return res.status(400).json({ error: "message too long" });

    const supports = parseSupported(req.body?.cards_supported);

    const history = Array.isArray(req.body?.history) ? req.body.history.slice(-6) : [];
    const cleanHistory = history
      .filter((m) => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
      .map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));

    const messages = [
      { role: "system", content: buildSystemMessage(req.body) },
      ...cleanHistory,
      { role: "user", content: message },
    ];

    let cards = null;

    for (let i = 0; i < 5; i++) {
      const completion = await groq.chat.completions.create({
        model: MODEL,
        messages,
        tools,
        tool_choice: "auto",
        temperature: 0.1,
        max_tokens: 1500,
        reasoning_effort: "low",
      });

      const msg = completion.choices[0].message;

      if (!msg.tool_calls || msg.tool_calls.length === 0) {
        const reply = finalReply(msg.content, cards);
        return res.json(cards ? { reply, cards } : { reply });
      }

      messages.push({
        role: "assistant",
        content: msg.content || "",
        tool_calls: msg.tool_calls,
      });

      for (const call of msg.tool_calls) {
        let forModel;
        try {
          const args = JSON.parse(call.function.arguments || "{}");
          const fn = handlers[call.function.name];
          if (!fn) {
            forModel = { error: "Unknown tool" };
          } else {
            const { data, brief, card } = await fn(args);
            const shown = Boolean(card) && supports.has(card.type);
            cards = shown ? card : null;
            forModel = shown
              ? { ...(brief || { count: data?.count }), cards_shown: true }
              : { ...data, cards_shown: false };
          }
        } catch (err) {
          console.error(err);
          cards = null;
          forModel = { error: "Failed to read data" };
        }
        messages.push({
          role: "tool",
          tool_call_id: call.id,
          content: JSON.stringify(forModel),
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