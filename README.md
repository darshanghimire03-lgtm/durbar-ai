# Durbar AI (Vercel-ready)

FastAPI backend for the Durbar AI assistant, deployed as a Vercel Python serverless function.

## Structure
- `api/index.py`   Vercel entrypoint (imports `app.main:app`)
- `vercel.json`    routing + function duration
- `vercel.env.json` reference list of env vars
- `scripts/set-vercel-env.sh` push `.env` to Vercel

## Deploy
```bash
npm i -g vercel
vercel login
vercel link
bash scripts/set-vercel-env.sh .env   # or add vars in the dashboard
vercel --prod
```
Check: `https://durbar-ai.vercel.app/health` -> `ok`

## Local dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 3000
```

## Notes
- Set `UPSTASH_REDIS_REST_URL`/`TOKEN` (or install Upstash from the Vercel Marketplace, which sets `KV_REST_API_*`) for rate limits shared across instances. Without it, limits are per-instance.
- `maxDuration` is 60s. Raise it in `vercel.json` if your plan allows.
- Set `CORS_ORIGINS` to your frontend domain in production.