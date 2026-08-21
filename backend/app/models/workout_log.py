"""
WorkoutLog and WorkoutExercise ORM models.

A WorkoutLog is a completed or in-progress session. Each log has an ordered
list of WorkoutExercises (the actual exercises performed with their sets/reps).
Rejection events live in rejection.py and reference exercises directly.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    workout_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # e.g. "push", "pull", "legs", "full_body", "custom"

    source: Mapped[str] = mapped_column(String(20), default="daily")
    # "daily" | "custom_builder" | "demo"

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    exercises: Mapped[list["WorkoutExercise"]] = relationship(
        "WorkoutExercise", back_populates="log", cascade="all, delete-orphan", order_by="WorkoutExercise.position"
    )

    def __repr__(self) -> str:
        return f"<WorkoutLog id={self.id} user_id={self.user_id} type={self.workout_type!r}>"


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    log_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_logs.id"), index=True)

    exercise_id: Mapped[str] = mapped_column(String(100), index=True)
    # References Exercise.id from exercises.json (string slug, e.g. "push_up")

    exercise_name: Mapped[str] = mapped_column(String(200))
    # Denormalized for easy display without joining to the JSON dataset

    position: Mapped[int] = mapped_column(Integer, default=0)
    # Order within the workout

    sets: Mapped[int] = mapped_column(Integer, default=3)
    reps: Mapped[str] = mapped_column(String(20), default="10")
    # Stored as string to support ranges like "8-12" or "AMRAP"

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=60)

    # Whether the user liked this exercise during the session
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "liked" | "disliked" | "rejected" | None

    # If this was a substitution, record what it replaced
    substituted_for_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    log: Mapped["WorkoutLog"] = relationship("WorkoutLog", back_populates="exercises")

    def __repr__(self) -> str:
        return f"<WorkoutExercise id={self.id} exercise={self.exercise_name!r} sets={self.sets}x{self.reps}>"
