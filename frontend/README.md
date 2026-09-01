# VectorFit — Frontend (Stage 10)

React + TypeScript client for the VectorFit API. Mobile-first, works on desktop,
light/dark aware.

## Stack

- **Vite + React 19 + TypeScript**
- **React Router** — client routing
- **TanStack Query** — server state / caching / mutations
- **Recharts** — charts (code-split into the Progress route only)
- Hand-written CSS with design tokens + CSS Modules — no UI kit

## Run

```bash
# 1. backend must be running (from ../backend):
#    uvicorn app.main:app --reload         → http://localhost:8000

# 2. this app:
npm install
cp .env.example .env.local        # optional — only if the API isn't on :8000
npm run dev                        # → http://localhost:5173
```

The backend allows `http://localhost:5173` for CORS by default
(`FRONTEND_ORIGIN` in `backend/.env`).

`npm run build` → static bundle in `dist/`. `npm run lint` → oxlint.

## Structure

```
src/
  main.tsx            providers: QueryClient, Router, Toast, User
  App.tsx             routing + auth gate (lazy-loads all screens but Today)
  context/UserContext active user id (localStorage; ?as=<id> deep-link)
  lib/
    api.ts            typed fetch client for every endpoint
    types.ts          API response shapes
    format.ts         date / prescription / label helpers
    workout.ts        client-side session-time estimate
  components/
    shell/            responsive nav — bottom tabs (mobile) / sidebar (desktop)
    ui/               Card, Button, Chip, Pill, Stat, Segmented, Sheet, Toast, …
    charts/           Recharts wrappers + the consistency calendar
    workout/          ExerciseItem, SessionRunner (check-off + finish flow)
    builder/          ExercisePicker (search + filters + suggestions)
    MuscleMap.tsx     inlines the server's anatomical SVG, scoped + trimmed
  screens/
    Onboarding  Today  Plan  Builder  Progress  History  WorkoutDetail  Profile
```

## Screens

| Route | What |
|---|---|
| `/` | **Today** — generate/run today's workout, check off, finish with feedback |
| `/plan` | week strip · saved templates · "Build a workout" |
| `/plan/build[/:id]` | **Builder** — name/type, add exercises (search + filter chips + type-scoped suggestions), edit sets/reps/time/notes, reorder, live analysis |
| `/progress` | summary tiles · **muscle map** · muscle-load / volume / patterns / balance / consistency charts · daily habits · swaps & pushback · injuries · PRs |
| `/progress/history` · `/progress/workout/:id` | full history · session detail (also acts as the runner for in-progress custom sessions) |
| `/profile` | goals · equipment · injuries (add / heal) · settings · log today's steps/sleep/weight/energy · switch profile |
