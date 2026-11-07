# Durbar AI v0.5

A knowledge assistant for the Durbar school app. Python + FastAPI + Firebase Realtime Database (REST API, no Admin SDK, no service-account key), built to run on Render's free plan.

- **Hybrid brain.** The rule engine answers what it understands instantly and for free (holidays, notes, profiles, small talk). Anything else goes to an **Ollama** model (official `ollama` Python client), which can chat, explain topics, and look up *real* school data through tools. It never has to guess holidays or notes.
- Ollama is **optional**: with `OLLAMA_MODEL` unset it runs exactly as the rule-only version.
- **Read-only**: it only sends HTTP GET requests to Firebase.
- No login/auth system in this version.

## What it can do

| Ask | Example |
|---|---|
| Small talk (from `knowledge.json`) | `hi`, `how are you`, `who are you`, `नमस्ते` |
| Next holiday / vacation / festival | `When is the next holiday?`, `Aba next chhuti kahile ho?`, `अर्को बिदा कहिले हो?` |
| Next exam / school event | `next exam`, `next school event` |
| Notes, PDFs, images, YouTube links | `Give me a computer note`, `Find English notes`, `Give me the mathematics PDF`, `Computer ko note deu` |
| Anything else (needs Ollama) | `Explain photosynthesis simply`, `Is there any celebration coming up?`, follow-ups like `and why?` |
| Anything else (rule-only mode) | `I don't know that yet. You can teach me!` |

Holiday logic: today's Bikram Sambat (BS) date is computed in Nepal time (UTC+5:45) with the `nepali-datetime` package, the calendar is read from `calendar/{BSyear}/{month}/{type}/{eventId}`, multi-day events use `startMonth/startDay/endMonth/endDay`, and the closest event that has not finished yet is returned (an event happening right now is reported as "going on right now"). If nothing is found, it says so. It never invents holidays. Records with missing date fields are skipped.

"Holiday" means types `emergency`, `vacation`, `festival`. Saying "vacation", "festival", "emergency", "exam/test" or "school event" narrows to that type.

## Project files

```
durbar-ai/
├── main.py            FastAPI app and endpoints
├── config.py          environment variables and settings
├── ai_engine.py       understanding + answering logic
├── llm.py             Ollama brain: tools, session memory, streaming
├── tests/             pytest suite (fake Firebase + fake Ollama)
├── knowledge.json     phrases, keywords, aliases (edit this to teach it)
├── firebase_data.py   read-only Firebase REST access (+ short cache)
├── requirements.txt
├── render.yaml
├── .env.example
└── README.md
```

## 1. Firebase setup

No private key or Admin SDK is used. The backend reads your database over its REST URL, so access is controlled entirely by your **database rules**.

1. Firebase Console -> **Realtime Database**. Copy the database URL, e.g. `https://darbarhigh-4c642-default-rtdb.firebaseio.com`.
2. Open the **Rules** tab and allow public read on **only** `calendar` and `units`, with writes blocked everywhere. Merge this with your existing rules (the Android app may need others):

```json
{
  "rules": {
    "calendar": { ".read": true, ".write": false },
    "units":    { ".read": true, ".write": false }
  }
}
```

3. Everything else stays private by default (no rule = no access), so user data is not exposed.

> **Important:** public read means anyone who knows your database URL can read `calendar` and `units` directly, not just through Durbar AI. Make sure those two paths contain nothing private (no emails, phone numbers or student data). The AI never returns `createdBy`, but the rule itself would still allow reading it.

## 1b. Ollama setup (optional)

Render's free plan cannot run a model itself, so point Durbar AI at an Ollama server you can reach:

- **Ollama cloud:** `OLLAMA_HOST=https://ollama.com`, `OLLAMA_API_KEY=<key from ollama.com>`, `OLLAMA_MODEL=<a model that supports tools>`.
- **Your own server / PC:** install Ollama, `ollama pull <model>`, expose it over HTTPS, then `OLLAMA_HOST=https://your-host`, `OLLAMA_MODEL=<model>`.

Pick a model that supports tool calling (needed for school-data lookups). `/health` reports `"llm": "connected"`, `"model_missing"`, `"error"` or `"disabled"`.

How it stays honest: the model gets three tools, `get_school_calendar`, `find_study_notes` and `find_person`, that run the same Firebase lookups as the rules. The system prompt forbids inventing dates, notes, links or people, tells it to treat tool text as data (not instructions), and includes today's AD and BS date. Tool rounds are capped (`LLM_MAX_TOOL_ROUNDS`, default 2); replies are capped by `OLLAMA_MAX_TOKENS`.

Chat memory: send the same `session_id` with each message to keep context (last 6 turns, in memory, expires after 30 min idle, so it resets on redeploy/sleep).

Cost control: LLM calls (not rule answers) are limited per client IP, 20 per minute by default (`LLM_RATE_LIMIT`, `LLM_RATE_WINDOW`). If Ollama is down, users get the normal fallback message.

## 2. Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set FIREBASE_DATABASE_URL
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs for interactive docs.

## 3. Deploy to Render

1. Push this folder to a GitHub repo (`.env` is git-ignored).
2. Render -> **New -> Blueprint** (uses `render.yaml`) or **New -> Web Service** with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. In **Environment**, add `FIREBASE_DATABASE_URL` with your database URL (that is the only secret-free variable you need).
4. Deploy, then open `https://YOUR-SERVICE.onrender.com/health`. `"firebase": "connected"` means it works.

Free-plan services sleep after inactivity, so the first request can take ~30-50 seconds.

Optional env vars: `CACHE_TTL_SECONDS` (default 60), `ALLOWED_ORIGINS` (default `*`, set your domain for web use).

## 4. API

| Method | Path | Returns |
|---|---|---|
| GET | `/` | `{"service":"Durbar AI","version":"0.5","status":"running","llm":"enabled"}` |
| GET | `/health` | `{"status":"ok","firebase":"connected","llm":"connected"}` (firebase: `not_configured` / `error`; llm: `disabled` / `model_missing` / `error`) |
| POST | `/chat` | `{"reply":"..."}`; body `{"message": "...", "session_id": "optional"}` |
| POST | `/chat/stream` | Server-Sent Events: `data: {"delta":"..."}` chunks, then `data: {"done":true}` |

Test examples:

```bash
BASE=http://127.0.0.1:8000     # or https://YOUR-SERVICE.onrender.com

curl $BASE/
curl $BASE/health

curl -X POST $BASE/chat -H "Content-Type: application/json" \
     -d '{"message": "hi"}'

curl -X POST $BASE/chat -H "Content-Type: application/json" \
     -d '{"message": "When is the next holiday?"}'

curl -X POST $BASE/chat -H "Content-Type: application/json" \
     -d '{"message": "Aba next chhuti kahile ho?"}'

curl -X POST $BASE/chat -H "Content-Type: application/json" \
     -d '{"message": "Computer ko note deu"}'

curl -X POST $BASE/chat -H "Content-Type: application/json" \
     -d '{"message": "Give me the mathematics PDF"}'

# needs Ollama; stream tokens as they are generated
curl -N -X POST $BASE/chat/stream -H "Content-Type: application/json" \
     -d '{"message": "Explain gravity simply", "session_id": "demo1"}'
```

Run the tests (no network, no Firebase, no Ollama needed): `pip install pytest && python -m pytest tests`.

## 5. Teaching it new things

Edit `knowledge.json`; no code changes needed:

- `responses`: add `"phrase": "reply"` for new small talk.
- `intents.calendar`: add words (Nepali, English, Nepanglish) that trigger holiday/exam/event lookups.
- `intents.notes_words`: words that mean "I want study material".
- `subjects`: add a subject and its spellings, e.g. `"health": ["health", "swasthya", "स्वास्थ्य"]`. The canonical name should match (or start like) your Firebase `subjectKey`.
- `stopwords`: filler words ignored when searching notes.

## Notes and limitations

- Calendar month keys may be numbers (`1`-`12`) or names (`Baisakh`...). Firebase may return months as a list; both are handled.
- Date fields used: `startMonth`, `startDay`, `endMonth`, `endDay` (single-day events may use `day`). Month falls back to the month key in the path.
- Notes matching is basic keywords (with simple stem matching like `program`~`programming`); title, subject, unit name and description are searched. Up to 3 notes are returned, each with PDF, image and YouTube URLs.
- The API is public and unauthenticated by design in this version. Only the LLM path is rate limited; add auth before wide release.
- Tested here with a fake Firebase and a fake Ollama client (no network in the build sandbox); FastAPI and the real `ollama` package were not installed there. Do a live check of `/health`, `/chat` and `/chat/stream` after deploying.
