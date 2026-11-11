import "dotenv/config";
import express from "express";
import cors from "cors";
import { cleanReply } from "./lib/helpers.js";
import { CARD_TYPES, DEFAULT_SUPPORTED, introFor } from "./lib/cards.js";
import { buildSystemMessage } from "./lib/prompt.js";
import { availableModels, defaultModel, findModel, publicModel } from "./lib/models.js";
import { createChat } from "./lib/llm.js";
import { handlers } from "./tools/handlers.js";
import { tableToHtml } from "./lib/table.js";

const PORT = process.env.PORT || 3000;

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

function finalReply(content, shown) {
  let reply = cleanReply(content);
  if (shown) {
    const tooLong = reply.length > 160 || reply.includes("\n") || /https?:\/\//i.test(reply);
    if (!reply || tooLong) reply = introFor(shown);
  } else if (!reply) {
    reply = "Sorry, I could not answer that.";
  }
  return reply;
}

app.get("/", (req, res) => {
  const def = defaultModel();
  res.json({ name: "Durbar AI", status: "ok", default_model: def ? def.id : null });
});

app.get("/health", (req, res) => res.status(200).send("ok"));

app.get("/cards", (req, res) =>
  res.json({ card_types: CARD_TYPES, default_supported: DEFAULT_SUPPORTED })
);

app.get("/models", (req, res) => {
  const def = defaultModel();
  res.json({
    default: def ? def.id : null,
    models: availableModels().map(publicModel),
  });
});

app.post("/chat", rateLimit, async (req, res) => {
  try {
    const message = String(req.body?.message ?? "").trim();
    if (!message) return res.status(400).json({ error: "message is required" });
    if (message.length > 1000) return res.status(400).json({ error: "message too long" });

    const requested = req.body?.model;
    let entry;
    if (requested) {
      entry = findModel(String(requested));
      if (!entry) {
        return res.status(400).json({
          error: "Unknown or unavailable model",
          available: availableModels().map((m) => m.id),
        });
      }
    } else {
      entry = defaultModel();
    }
    if (!entry) return res.status(503).json({ error: "No AI model is configured on the server." });

    const supports = parseSupported(req.body?.cards_supported);

    const history = Array.isArray(req.body?.history) ? req.body.history.slice(-8) : [];
    const cleanHistory = history
      .filter((m) => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
      .map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));

    const chat = createChat(entry, buildSystemMessage(req.body), cleanHistory, message);

    const ctx = { sessionKey: String(req.body?.session_id || req.ip).slice(0, 100) };

    let cards = null;
    let table = null;

    for (let i = 0; i < 6; i++) {
      const { text, calls } = await chat.step();

      if (calls.length === 0) {
        const reply = finalReply(text, cards || table);
        const body = { reply };
        if (cards) body.cards = cards;
        if (table) {
          body.table = table;
          body.html = tableToHtml(table);
        }
        return res.json({ ...body, model: entry.id });
      }

      const results = [];

      for (const call of calls) {
        let forModel;
        try {
          const fn = handlers[call.name];
          if (!fn) {
            forModel = { error: "Unknown tool" };
          } else {
            const { data, brief, card, table: tbl } = await fn(call.args, ctx);
            const shown = !tbl && Boolean(card) && supports.has(card.type);
            cards = shown ? card : null;
            table = tbl || null;
            if (tbl) forModel = { ...(brief || { count: data?.count }), table_shown: true };
            else if (shown) forModel = { ...(brief || { count: data?.count }), cards_shown: true };
            else forModel = { ...data, cards_shown: false };
          }
        } catch (err) {
          console.error(err);
          cards = null;
          table = null;
          forModel = { error: "Failed to read data" };
        }
        results.push({ id: call.id, apiId: call.apiId, name: call.name, response: forModel });
      }

      chat.addResults(results);
    }

    res.json({
      reply: "Sorry, I could not complete that request. Please try again.",
      model: entry.id,
    });
  } catch (err) {
    console.error(err);
    if (err?.status === 429) {
      return res.status(429).json({
        error: "This model is busy right now. Please try another model.",
      });
    }
    res.status(500).json({ error: "Something went wrong. Please try again." });
  }
});

app.listen(PORT, () => {
  const names = availableModels().map((m) => m.id).join(", ") || "none";
  console.log(`Durbar AI running on port ${PORT}. Models: ${names}`);
});