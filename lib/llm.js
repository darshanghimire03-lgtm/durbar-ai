import Groq from "groq-sdk";
import { tools } from "../tools/definitions.js";

const GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models";
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const MAX_OUTPUT_TOKENS = 4000;

let groqClient = null;

function getGroq() {
  if (!groqClient) groqClient = new Groq({ apiKey: process.env.GROQ_API_KEY });
  return groqClient;
}

function parseArgs(raw) {
  try {
    return JSON.parse(raw || "{}");
  } catch {
    return {};
  }
}

function groqSession(entry, system, history, message) {
  const messages = [
    { role: "system", content: system },
    ...history,
    { role: "user", content: message },
  ];

  return {
    async step() {
      const completion = await getGroq().chat.completions.create({
        model: entry.model,
        messages,
        tools,
        tool_choice: "auto",
        temperature: 0.1,
        max_tokens: 2500,
        reasoning_effort: "low",
      });

      const msg = completion.choices[0].message;
      const calls = (msg.tool_calls || []).map((c) => ({
        id: c.id,
        name: c.function.name,
        args: parseArgs(c.function.arguments),
      }));

      if (calls.length) {
        messages.push({
          role: "assistant",
          content: msg.content || "",
          tool_calls: msg.tool_calls,
        });
      }
      return { text: msg.content || "", calls };
    },

    addResults(results) {
      for (const r of results) {
        messages.push({
          role: "tool",
          tool_call_id: r.id,
          content: JSON.stringify(r.response),
        });
      }
    },
  };
}

function openrouterSession(entry, system, history, message) {
  const messages = [
    { role: "system", content: system },
    ...history,
    { role: "user", content: message },
  ];

  return {
    async step() {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 90000);
      let res;
      try {
        res = await fetch(OPENROUTER_URL, {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
            "X-Title": "Durbar AI",
          },
          body: JSON.stringify({
            model: entry.model,
            messages,
            tools,
            tool_choice: "auto",
            temperature: 0.2,
            max_tokens: 2500,
          }),
        });
      } finally {
        clearTimeout(timer);
      }

      let data = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }

      if (!res.ok || !data || data.error) {
        const detail = data?.error?.message || `status ${res.status}`;
        const err = new Error(`OpenRouter ${entry.model}: ${String(detail).slice(0, 300)}`);
        err.status = res.ok ? Number(data?.error?.code) || 502 : res.status;
        throw err;
      }

      const msg = data.choices?.[0]?.message;
      if (!msg) {
        const err = new Error(`OpenRouter ${entry.model}: empty response`);
        err.status = 502;
        throw err;
      }

      const calls = (msg.tool_calls || []).map((c, i) => ({
        id: c.id || `call_${i}`,
        name: c.function?.name,
        args: parseArgs(c.function?.arguments),
      }));

      if (calls.length) {
        messages.push({
          role: "assistant",
          content: msg.content || "",
          tool_calls: msg.tool_calls.map((c, i) => ({ ...c, id: c.id || `call_${i}` })),
          ...(msg.reasoning_details ? { reasoning_details: msg.reasoning_details } : {}),
        });
      }
      return { text: typeof msg.content === "string" ? msg.content : "", calls };
    },

    addResults(results) {
      for (const r of results) {
        messages.push({
          role: "tool",
          tool_call_id: r.id,
          content: JSON.stringify(r.response),
        });
      }
    },
  };
}

function toGeminiSchema(s) {
  if (!s || typeof s !== "object") return s;
  const out = {};
  if (s.type) out.type = String(s.type).toUpperCase();
  if (s.description) out.description = s.description;
  if (s.enum) out.enum = s.enum;
  if (s.required) out.required = s.required;
  if (s.items) out.items = toGeminiSchema(s.items);
  if (s.properties) {
    out.properties = {};
    for (const [k, v] of Object.entries(s.properties)) out.properties[k] = toGeminiSchema(v);
  }
  return out;
}

const geminiTools = [
  {
    functionDeclarations: tools.map((t) => {
      const p = t.function.parameters;
      const hasProps = p && p.properties && Object.keys(p.properties).length > 0;
      return {
        name: t.function.name,
        description: t.function.description,
        ...(hasProps ? { parameters: toGeminiSchema(p) } : {}),
      };
    }),
  },
];

function toGeminiContents(history, message) {
  const out = [];
  for (const m of history) {
    if (!m.content || !m.content.trim()) continue;
    const role = m.role === "assistant" ? "model" : "user";
    const last = out[out.length - 1];
    if (last && last.role === role) last.parts[0].text += "\n" + m.content;
    else out.push({ role, parts: [{ text: m.content }] });
  }
  while (out.length && out[0].role === "model") out.shift();

  const last = out[out.length - 1];
  if (last && last.role === "user") last.parts[0].text += "\n" + message;
  else out.push({ role: "user", parts: [{ text: message }] });
  return out;
}

function geminiSession(entry, system, history, message) {
  const contents = toGeminiContents(history, message);

  return {
    async step() {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 60000);
      let res;
      try {
        res = await fetch(`${GEMINI_URL}/${entry.model}:generateContent`, {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": process.env.GEMINI_API_KEY,
          },
          body: JSON.stringify({
            systemInstruction: { parts: [{ text: system }] },
            contents,
            tools: geminiTools,
            toolConfig: { functionCallingConfig: { mode: "AUTO" } },
            generationConfig: { maxOutputTokens: MAX_OUTPUT_TOKENS },
          }),
        });
      } finally {
        clearTimeout(timer);
      }

      if (!res.ok) {
        const body = await res.text();
        const err = new Error(`Gemini ${res.status}: ${body.slice(0, 300)}`);
        err.status = res.status;
        throw err;
      }

      const data = await res.json();
      const content = data.candidates?.[0]?.content;
      const parts = content?.parts || [];

      const text = parts
        .filter((p) => typeof p.text === "string" && !p.thought)
        .map((p) => p.text)
        .join("");

      const calls = parts
        .filter((p) => p.functionCall)
        .map((p, i) => ({
          id: p.functionCall.id || `call_${i}`,
          apiId: p.functionCall.id || null,
          name: p.functionCall.name,
          args: p.functionCall.args || {},
        }));

      if (calls.length && content) {
        contents.push({ role: "model", parts });
      }
      return { text, calls };
    },

    addResults(results) {
      contents.push({
        role: "user",
        parts: results.map((r) => ({
          functionResponse: {
            name: r.name,
            ...(r.apiId ? { id: r.apiId } : {}),
            response: r.response,
          },
        })),
      });
    },
  };
}

export function createChat(entry, system, history, message) {
  if (entry.provider === "gemini") return geminiSession(entry, system, history, message);
  if (entry.provider === "openrouter") return openrouterSession(entry, system, history, message);
  return groqSession(entry, system, history, message);
}