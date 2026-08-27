"""Pydantic schemas for daily/weekly program responses (Stage 7)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class WorkoutExerciseOut(BaseModel):
    id: int
    exercise_id: str
    exercise_name: str
    position: int
    sets: int
    reps: str | None = None
    duration_seconds: int | None = None
    weight_kg: float | None = None
    rest_seconds: int
    notes: str | None = None
    feedback: str | None = None
    substituted_for_id: str | None = None
    substituted_for_name: str | None = None
    substitution_note: str | None = None

    model_config = {"from_attributes": True}


class WorkoutLogOut(BaseModel):
    id: int
    user_id: int
    name: str | None = None
    workout_type: str | None
    workout_label: str | None = None
    source: str
    is_template: bool = False
    started_at: datetime
    completed_at: datetime | None
    notes: str | None = None
    exercises: list[WorkoutExerciseOut]

    model_config = {"from_attributes": True}


class DayProgramOut(BaseModel):
    day_index: int
    date: date
    is_rest: bool
    workout: WorkoutLogOut | None = None
    warnings: list[str] = []


class WeekProgramOut(BaseModel):
    days: list[DayProgramOut]
