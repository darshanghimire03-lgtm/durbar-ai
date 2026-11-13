# Durbar AI (Vercel)

FastAPI backend for the Durbar AI assistant, deployed as a Vercel Python serverless function.

## Endpoints
- `POST /chat` returns one JSON reply with `reply`, `cards`, `model`, `steps` and `user`
- `POST /chat/stream` streams server-sent events: `start`, `status`, `delta`, `reset`, `done`, `error`
- `GET /models`, `GET /cards`, `GET /health`

## Request body
`message`, `model`, `history`, `cards_supported`, `today_bs`, `session_id`, `user` (with `uid`), `id_token`

## Who is talking
With `FIREBASE_API_KEY` set, the server verifies `id_token` and reads the role from the users data. Without it, the `uid` sent by the app is trusted.

## Standing instructions
Store text in the Firebase node `ai_instructions` as a string, or as entries like `{ "text": "...", "active": true }`. Keep that node writable only by professors, captains and moderators in your database rules.

## Deploy
```bash
npm i -g vercel
vercel login
vercel link
bash scripts/set-vercel-env.sh .env
vercel --prod
```
Check: `https://durbar-ai.vercel.app/health` returns `ok`

## Local dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 3000
```

## Notes
- Set `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` (or add Upstash from the Vercel Marketplace) for rate limits shared across instances.
- `maxDuration` is 60s in `vercel.json`. Raise it if your plan allows.
- Set `CORS_ORIGINS` to your frontend domain in production.