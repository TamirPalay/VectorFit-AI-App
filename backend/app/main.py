from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine

# Import all models so SQLAlchemy registers them before create_all
import app.models.user  # noqa: F401
import app.models.workout_log  # noqa: F401
import app.models.rejection  # noqa: F401
import app.models.daily_metric  # noqa: F401

from app.routers import (
    profile, exercises, suggestibility, substitution, explanation, daily_program, custom_workout,
    metrics, workout_logs, dashboard,
)

app = FastAPI(
    title="VectorFit API",
    description="Injury- and preference-aware fitness app backend",
    version="0.1.0",
)

# FRONTEND_ORIGIN may be a single URL or a comma-separated list (prod + previews).
_allowed_origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel preview deploys
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(exercises.router)
app.include_router(suggestibility.router)
app.include_router(substitution.router)
app.include_router(explanation.router)
app.include_router(daily_program.router)
app.include_router(custom_workout.router)
app.include_router(metrics.router)
app.include_router(workout_logs.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def startup():
    """Create tables, optionally seed demo data, and load the exercise index."""
    Base.metadata.create_all(bind=engine)

    # On hosts with an ephemeral disk (e.g. Render free tier) the SQLite file is
    # wiped on every deploy/restart. Re-seed the demo users on boot if the DB is
    # empty. run_seed() is idempotent, so this is a no-op once data exists.
    if settings.seed_on_startup:
        from app.database import SessionLocal
        from app.models.user import User
        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                print("[startup] Empty database - seeding demo data...")
                from app.data.seed_demo import run_seed
                run_seed()
                print("[startup] Seed complete.")
        except Exception as exc:  # don't let a seed failure block app boot
            print(f"[startup] WARNING: demo seed failed: {exc!r}")
        finally:
            db.close()

    from app.ml.embeddings import ExerciseIndex
    app.state.exercise_index = ExerciseIndex.load()
    print(f"[startup] Exercise index loaded: {len(app.state.exercise_index)} exercises")


@app.get("/health")
def health_check():
    n = len(getattr(app.state, "exercise_index", []) or [])
    return {"status": "ok", "version": "0.1.0", "exercises_loaded": n}
