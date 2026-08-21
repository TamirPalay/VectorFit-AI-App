from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine

# Import all models so SQLAlchemy registers them before create_all
import app.models.user  # noqa: F401
import app.models.workout_log  # noqa: F401
import app.models.rejection  # noqa: F401

from app.routers import profile, exercises

# Later stages will add:
# from app.routers import suggestibility, substitution, daily_program, custom_builder, dashboard

app = FastAPI(
    title="VectorFit API",
    description="Injury- and preference-aware fitness app backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(exercises.router)


@app.on_event("startup")
def startup():
    """Create database tables and load the exercise index into app.state."""
    Base.metadata.create_all(bind=engine)

    from app.ml.embeddings import ExerciseIndex
    app.state.exercise_index = ExerciseIndex.load()
    print(f"[startup] Exercise index loaded: {len(app.state.exercise_index)} exercises")


@app.get("/health")
def health_check():
    n = len(getattr(app.state, "exercise_index", []) or [])
    return {"status": "ok", "version": "0.1.0", "exercises_loaded": n}
