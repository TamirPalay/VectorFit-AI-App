"""
Pydantic schemas for User and Injury.

Separating schemas from ORM models keeps the API contract explicit and prevents
internal fields (like JSON columns) from leaking out.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


FitnessLevel = Literal["beginner", "intermediate", "advanced"]
InjurySeverity = Literal["mild", "moderate", "severe"]
PainType = Literal["sharp_acute", "dull_stiff", "old_recurring", "new_unsure"]

VALID_GOALS = {
    "weight_loss", "muscle_gain", "hypertrophy", "strength", "endurance",
    "mobility", "general_fitness", "sport_specific",
}

VALID_EQUIPMENT = {
    "barbell", "dumbbells", "kettlebell", "pull_up_bar", "resistance_bands",
    "cables", "machines", "bodyweight", "trx", "bench", "squat_rack",
}

VALID_MOVEMENT_PREFS = {"free_weights", "machines", "cables", "bodyweight", "mixed"}


# ── Injury schemas ─────────────────────────────────────────────────────────────

class InjuryCreate(BaseModel):
    body_part: str = Field(..., min_length=2, max_length=100)
    severity: InjurySeverity = "moderate"
    pain_type: PainType | None = None
    recovery_expectation_days: int | None = Field(None, ge=1, le=730)
    notes: str | None = Field(None, max_length=1000)


class InjuryUpdate(BaseModel):
    severity: InjurySeverity | None = None
    pain_type: PainType | None = None
    recovery_expectation_days: int | None = Field(None, ge=1, le=730)
    notes: str | None = None


class InjuryOut(BaseModel):
    id: int
    body_part: str
    severity: InjurySeverity
    pain_type: PainType | None
    recovery_expectation_days: int | None
    notes: str | None
    is_active: bool
    healed_at: datetime | None
    created_at: datetime
    expected_recovery_date: datetime | None

    model_config = {"from_attributes": True}


# ── User schemas ───────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr

    age: int | None = Field(None, ge=10, le=120)
    weight_kg: float | None = Field(None, ge=20, le=400)
    height_cm: float | None = Field(None, ge=50, le=280)

    goals: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    movement_preferences: list[str] = Field(default_factory=list)

    fitness_level: FitnessLevel = "beginner"
    experience_level: FitnessLevel = "beginner"
    days_per_week: int = Field(3, ge=1, le=7)
    minutes_per_session: int = Field(45, ge=10, le=300)

    @model_validator(mode="after")
    def validate_list_fields(self) -> "UserCreate":
        invalid_goals = set(self.goals) - VALID_GOALS
        if invalid_goals:
            raise ValueError(f"Unknown goals: {invalid_goals}. Valid: {VALID_GOALS}")
        invalid_eq = set(self.equipment) - VALID_EQUIPMENT
        if invalid_eq:
            raise ValueError(f"Unknown equipment: {invalid_eq}. Valid: {VALID_EQUIPMENT}")
        invalid_prefs = set(self.movement_preferences) - VALID_MOVEMENT_PREFS
        if invalid_prefs:
            raise ValueError(f"Unknown movement preferences: {invalid_prefs}. Valid: {VALID_MOVEMENT_PREFS}")
        return self


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    age: int | None = Field(None, ge=10, le=120)
    weight_kg: float | None = Field(None, ge=20, le=400)
    height_cm: float | None = Field(None, ge=50, le=280)

    goals: list[str] | None = None
    equipment: list[str] | None = None
    movement_preferences: list[str] | None = None

    fitness_level: FitnessLevel | None = None
    experience_level: FitnessLevel | None = None
    days_per_week: int | None = Field(None, ge=1, le=7)
    minutes_per_session: int | None = Field(None, ge=10, le=300)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    age: int | None
    weight_kg: float | None
    height_cm: float | None
    goals: list[str]
    equipment: list[str]
    movement_preferences: list[str]
    fitness_level: str
    experience_level: str
    days_per_week: int
    minutes_per_session: int
    created_at: datetime
    updated_at: datetime
    injuries: list[InjuryOut] = []

    model_config = {"from_attributes": True}
