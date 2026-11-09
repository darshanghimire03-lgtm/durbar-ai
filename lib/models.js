export function getAllModels() {
  return [
    {
      id: "groq-gpt-oss-120b",
      label: "Groq GPT-OSS 120B",
      provider: "groq",
      model: process.env.GROQ_MODEL || "openai/gpt-oss-120b",
      description: "Fast open model running on Groq",
    },
    {
      id: "gemini-flash-lite-latest",
      label: "Gemini Flash-Lite (Latest)",
      provider: "gemini",
      model: "gemini-flash-lite-latest",
      description: "Always points to the newest Flash-Lite",
    },
    {
      id: "gemini-3.5-flash-lite",
      label: "Gemini 3.5 Flash-Lite",
      provider: "gemini",
      model: "gemini-3.5-flash-lite",
      description: "Fastest and cheapest Gemini 3.5",
    },
    {
      id: "gemini-3.6-flash",
      label: "Gemini 3.6 Flash",
      provider: "gemini",
      model: "gemini-3.6-flash",
      description: "Smarter Gemini for harder questions",
    },
    {
      id: "or-nemotron-3.5-super-vl",
      label: "NVIDIA Nemotron 3.5 Super VL (Free)",
      provider: "openrouter",
      model: "nvidia/nemotron-3.5-super-vl:free",
      description: "Large reasoning model with 1M context, via OpenRouter",
    },
    {
      id: "or-flint",
      label: "Recursive Flint (Free)",
      provider: "openrouter",
      model: "recursive/flint-v1.0:free",
      description: "Reasoning and tool use model, via OpenRouter",
    },
    {
      id: "or-gemma-4-26b",
      label: "Google Gemma 4 26B A4B (Free)",
      provider: "openrouter",
      model: "google/gemma-4-26b-a4b-it:free",
      description: "Balanced Gemma model, via OpenRouter",
    },
    {
      id: "or-lfm-2.5-2.6b",
      label: "LiquidAI LFM2.5 2.6B (Free)",
      provider: "openrouter",
      model: "liquid/lfm-2.5-2.6b:free",
      description: "Very small and fast, simple questions only, via OpenRouter",
    },
  ];
}

function hasKey(provider) {
  if (provider === "groq") return Boolean(process.env.GROQ_API_KEY);
  if (provider === "gemini") return Boolean(process.env.GEMINI_API_KEY);
  if (provider === "openrouter") return Boolean(process.env.OPENROUTER_API_KEY);
  return false;
}

export function availableModels() {
  return getAllModels().filter((m) => hasKey(m.provider));
}

export function defaultModel() {
  const list = availableModels();
  if (!list.length) return null;
  const wanted = process.env.DEFAULT_MODEL;
  return list.find((m) => m.id === wanted) || list[0];
}

export function findModel(id) {
  return availableModels().find((m) => m.id === id) || null;
}

export function publicModel(m) {
  return {
    id: m.id,
    label: m.label,
    provider: m.provider,
    description: m.description,
  };
}