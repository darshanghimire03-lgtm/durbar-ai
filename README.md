# Durbar AI v0.2

A small, rule-based knowledge assistant for the Durbar school app. Python + FastAPI + Firebase Admin SDK, built to run on Render's free plan.

- No LLM, no paid APIs, no NLP framework: just phrase matching and keyword search.
- **Read-only**: it never writes to Firebase.
- No login/auth system in this version.

## What it can do

| Ask | Example |
|---|---|
| Small talk (from `knowledge.json`) | `hi`, `how are you`, `who are you`, `नमस्ते` |
| Next holiday / vacation / festival | `When is the next holiday?`, `Aba next chhuti kahile ho?`, `अर्को बिदा कहिले हो?` |
| Next exam / school event | `next exam`, `next school event` |
| Notes, PDFs, images, YouTube links | `Give me a computer note`, `Find English notes`, `Give me the mathematics PDF`, `Computer ko note deu` |
| Anything else | `I don't know that yet. You can teach me!` |

Holiday logic: today's Bikram Sambat (BS) date is computed in Nepal time (UTC+5:45) with the `nepali-datetime` package, the calendar is read from `calendar/{BSyear}/{month}/{type}/{eventId}`, multi-day events use `startMonth/startDay/endMonth/endDay`, and the closest event that has not finished yet is returned (an event happening right now is reported as "going on right now"). If nothing is found, it says so. It never invents holidays. Records with missing date fields are skipped.

"Holiday" means types `emergency`, `vacation`, `festival`. Saying "vacation", "festival", "emergency", "exam/test" or "school event" narrows to that type.

## Project files

```
durbar-ai/
├── main.py            FastAPI app and endpoints
├── config.py          environment variables and settings
├── ai_engine.py       understanding + answering logic
├── knowledge.json     phrases, keywords, aliases (edit this to teach it)
├── firebase_data.py   read-only Firebase access (+ short cache)
├── requirements.txt
├── render.yaml
├── .env.example
└── README.md
```

## 1. Firebase setup

1. Firebase Console -> **Project settings -> Service accounts -> Generate new private key**. A JSON file downloads. Keep it secret. Never commit it or put it in the Android app.
2. Copy your Realtime Database URL (Realtime Database page), e.g. `https://your-project-default-rtdb.firebaseio.com`.
3. Recommended database rules (this backend only needs `calendar` and `units`; the Android app keeps its own rules as needed, so merge rather than overwrite):

```json
{
  "rules": {
    "calendar": { ".read": true, ".write": false },
    "units":    { ".read": true, ".write": false }
  }
}
```

> **Important:** the Admin SDK bypasses database rules. Safety here comes from the code: it only reads `calendar` and `units`, never writes, and never returns `createdBy` or any user data. If your `calendar` or `units` contain anything private, remove it before using this version.

## 2. Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two values (JSON on ONE line)
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/docs for interactive docs.

## 3. Deploy to Render

1. Push this folder to a GitHub repo (`.env` is git-ignored).
2. Render -> **New -> Blueprint** (uses `render.yaml`) or **New -> Web Service** with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. In **Environment**, add:
   - `FIREBASE_DATABASE_URL`: your database URL
   - `FIREBASE_SERVICE_ACCOUNT_JSON`: paste the **entire** JSON file contents
4. Deploy, then open `https://YOUR-SERVICE.onrender.com/health`. `"firebase": "connected"` means it works.

Free-plan services sleep after inactivity, so the first request can take ~30-50 seconds.

Optional env vars: `CACHE_TTL_SECONDS` (default 60), `ALLOWED_ORIGINS` (default `*`, set your domain for web use).

## 4. API

| Method | Path | Returns |
|---|---|---|
| GET | `/` | `{"service":"Durbar AI","version":"0.2","status":"running"}` |
| GET | `/health` | `{"status":"ok","firebase":"connected"}` (or `not_configured` / `error`) |
| POST | `/chat` | `{"reply":"..."}` |

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
```

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
- The API is public and unauthenticated by design in this version. Consider adding rate limiting before wide release.
- Tested here with a fake Firebase and a stubbed web layer (no network in the build sandbox). Do a live check of `/health` and `/chat` after deploying.
