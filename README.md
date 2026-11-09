# Durbar AI

Backend for the Durbar school app assistant. It answers Durbar app questions from the Firebase database, reads the text inside notes PDFs, and answers general questions. The user can choose which AI model answers.

## Models

| App id | Name | Provider | Model ID |
|---|---|---|---|
| groq-gpt-oss-120b | Groq GPT-OSS 120B | Groq | value of GROQ_MODEL |
| gemini-flash-lite-latest | Gemini Flash-Lite (Latest) | Gemini | gemini-flash-lite-latest |
| gemini-3.5-flash-lite | Gemini 3.5 Flash-Lite | Gemini | gemini-3.5-flash-lite |
| gemini-3.6-flash | Gemini 3.6 Flash | Gemini | gemini-3.6-flash |
| or-nemotron-3.5-super-vl | NVIDIA Nemotron 3.5 Super VL (Free) | OpenRouter | nvidia/nemotron-3.5-super-vl:free |
| or-flint | Recursive Flint (Free) | OpenRouter | recursive/flint-v1.0:free |
| or-gemma-4-26b | Google Gemma 4 26B A4B (Free) | OpenRouter | google/gemma-4-26b-a4b-it:free |
| or-lfm-2.5-2.6b | LiquidAI LFM2.5 2.6B (Free) | OpenRouter | liquid/lfm-2.5-2.6b:free |

A model is shown to users only when the API key for its provider is set:

- GROQ_API_KEY enables the Groq model
- GEMINI_API_KEY enables the three Gemini models
- OPENROUTER_API_KEY enables the four OpenRouter models

## How it works

1. The app calls GET /models and shows the list in a model picker.
2. The user picks a model. The app saves the chosen id on the phone.
3. Every chat request sends that id in the model field.
4. The server runs the same tools (events, notes, PDFs, mock tests, people, posts, app updates) with the chosen model and returns the reply and optional cards.
5. If no model is sent, the server uses DEFAULT_MODEL, or the first available model.

## Setup

1. Run npm install
2. Copy .env.example to .env and fill in the values
3. Run npm start

Environment variables:

| Name | Required | Meaning |
|---|---|---|
| GROQ_API_KEY | At least one key | Enables the Groq model |
| GROQ_MODEL | No | Groq model name, default openai/gpt-oss-120b |
| GEMINI_API_KEY | At least one key | Enables the Gemini models. Get it from Google AI Studio |
| OPENROUTER_API_KEY | At least one key | Enables the OpenRouter free models. Get it from openrouter.ai |
| DEFAULT_MODEL | No | App id used when the app sends no model |
| FIREBASE_DATABASE_URL | Yes | Realtime Database URL |
| PORT | No | Default 3000 |

On Render, add the same variables in the service Environment tab.

## API

### GET /models

```json
{
  "default": "gemini-3.5-flash-lite",
  "models": [
    {
      "id": "or-gemma-4-26b",
      "label": "Google Gemma 4 26B A4B (Free)",
      "provider": "openrouter",
      "description": "Balanced Gemma model, via OpenRouter"
    }
  ]
}
```

### POST /chat

Request:

```json
{
  "message": "explain complement logic",
  "model": "or-gemma-4-26b",
  "history": [{ "role": "user", "content": "hi" }],
  "cards_supported": ["people", "notes"],
  "user": { "fullName": "Darshan Ghimire", "role": "captain", "classLevel": "11", "section": "B" },
  "today_bs": { "year": 2083, "month": 7, "day": 25 }
}
```

Response:

```json
{
  "reply": "...",
  "cards": { },
  "model": "or-gemma-4-26b"
}
```

The cards field is present only when the app shows cards. The model field tells which model answered.

Errors:

| Status | Meaning |
|---|---|
| 400 | Empty message, message too long, or unknown model id (the response lists available ids) |
| 429 | Too many requests, or the chosen model is busy. Suggest another model |
| 503 | No model is configured on the server |
| 500 | Unexpected server error |

### Other endpoints

- GET /health returns ok
- GET /cards lists supported card types

## Add the picker in the app

1. On opening the chat screen, call GET /models.
2. Show a dropdown or bottom sheet in the chat header with label and description for each model.
3. Group the list by the provider field if you want sections such as Gemini, Groq and OpenRouter (Free).
4. Save the selected id on the phone and select it again on next launch.
5. If the saved id is no longer in the list, use the default value from GET /models.
6. Send the selected id as model in every POST /chat.
7. On a 429 response, show the error text and let the user switch models.
8. Optionally show the label of the model from the response model field under each answer.

## Reading PDFs

When the user asks about the content of notes, the model calls read_pdf_notes. The server downloads the subject PDFs, extracts text, and sends the pages that best match the question. Scanned PDFs (images only) have no text and cannot be read. Up to 4 PDFs and about 12000 characters are used per question.

## Free OpenRouter models

- They cost nothing but have per-minute and per-day request limits, so they can answer slowly or return a busy error (429). Users can switch to another model.
- Some free endpoints may log prompts or use them for training. Prompts can include names and posts from the app, so keep a Gemini or Groq model as DEFAULT_MODEL.
- LFM2.5 2.6B is very small. It is fast but can be weak at tools and long answers. Use it for simple questions.
- Free model availability changes. If a model starts returning errors, check its ID on openrouter.ai and update lib/models.js.

## Add another model later

Add one entry in getAllModels in lib/models.js with a unique id, label, provider (groq, gemini or openrouter), the provider model ID and a description. Any OpenRouter model ID works with the openrouter provider as long as the model supports tool calling.

## Notes about Gemini

- Gemini 3.x models do not accept temperature, top_p or top_k, so the server never sends them.
- Tool calls keep the model's returned parts unchanged so Gemini thought signatures are preserved.

## Security

All API keys stay on the server. Never put them in the app.

## Troubleshooting

- A model is missing from /models: its provider API key is not set.
- 400 Unknown or unavailable model: the id sent does not match an id from /models.
- Gemini 400 or 404 errors in the logs: check the model ID and that the API key is valid.
- OpenRouter error saying no endpoints support tool use: that model cannot be used with this app. Remove it from lib/models.js.
- Empty or very short answers: try another model or check the server logs.