# VectorFit

An injury- and preference-aware fitness app. VectorFit builds daily and weekly
workout programs, then uses a vector-similarity engine to swap out any exercise
an injury or a stated preference rules out — keeping the muscle stimulus as close
as possible to the original. An LLM narrates *why* each swap was made; it never
makes the safety call itself.

- **Backend** — FastAPI + SQLAlchemy + SQLite, FAISS for 22-dim muscle-activation
  similarity search, pandas/matplotlib for the progress dashboard, Gemini
  (`google-genai`) for swap narration.
- **Frontend** — Vite + React 19 + TypeScript, React Router, TanStack Query,
  Recharts. Mobile-first, full light/dark.

## Local development

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env                             # then fill in GEMINI_API_KEY
python -m app.data.seed_demo                         # seed the 3 demo users
uvicorn app.main:app --reload                        # http://127.0.0.1:8000  (docs at /docs)
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                          # VITE_API_BASE defaults to http://localhost:8000
npm run dev                                          # http://localhost:5173
```

Demo users: **Tamir** (shoulder injury, all suggestibility states), **Morgan**
(beginner, no injuries), **Jordan** (knee injury). Pick one on the onboarding
screen, or deep-link with `?as=<id>`.

## Deployment

Backend → **Render** (free web service). Frontend → **Vercel**. Config lives in
`render.yaml` and `frontend/vercel.json`.

### 1. Backend on Render

1. render.com → **New → Blueprint** → select this repo. Render reads `render.yaml`.
2. After the first deploy, set these in the service's **Environment** tab:
   - `GEMINI_API_KEY` — your key. Enable billing on it: the free tier's 5 req/min
     cap will 429 the swap narration during a live demo.
   - `FRONTEND_ORIGIN` — your Vercel URL (step 2). `*.vercel.app` preview URLs are
     always allowed via regex, so you only need the production one here.
3. `SECRET_KEY` is generated automatically; `PYTHON_VERSION`, `LLM_PROVIDER`,
   `GEMINI_MODEL`, `SEED_ON_STARTUP` come from `render.yaml`.
4. Verify: `https://<service>.onrender.com/health` → `{"status":"ok","exercises_loaded":316}`.

**Notes**

- The SQLite disk is **ephemeral** on the free tier. `SEED_ON_STARTUP=true` re-seeds
  the demo users whenever the database comes up empty (the seeder is idempotent).
  Anything created through the live app is lost on the next deploy/restart. For
  durable data, point `DATABASE_URL` at a managed Postgres (Neon/Supabase) — the
  code is already Postgres-safe.
- Free instances sleep after ~15 min idle; the first request then takes ~50s
  (plus a few more seconds if it also has to re-seed). Hit `/health` to warm it
  before a demo.

### 2. Frontend on Vercel

1. vercel.com → **Add New → Project** → select this repo.
2. **Root Directory: `frontend`**. Framework preset auto-detects as Vite.
3. Environment variable: `VITE_API_BASE = https://<service>.onrender.com`.
4. Deploy. Then go back to Render and set `FRONTEND_ORIGIN` to the Vercel URL and
   redeploy the backend (CORS won't pass until it matches).

### 3. Smoke test

Open the Vercel URL, pick Tamir, and walk: **Today → generate workout**,
**Plan → week strip**, **Progress → muscle map + charts**, **Profile**. Watch the
browser Network tab for CORS errors or 500s.

## Repository layout

```
backend/          FastAPI app, engines, seed data, render.yaml target
  app/routers/     HTTP endpoints
  app/services/    suggestibility / substitution / daily-program / dashboard / LLM
  app/ml/          FAISS exercise index
  app/data/        exercises.json (316 labeled), seed_demo.py
frontend/          Vite + React SPA
data_pipeline/     one-off offline LLM labeling of exercises.json (not deployed)
```
