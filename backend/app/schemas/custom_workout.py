"""Pydantic schemas for the custom workout builder (Stage 8)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.workout import WorkoutExerciseOut, WorkoutLogOut

# Kept loose on purpose — the builder's workout_type is a free label the user
# picks (push/pull/legs/upper/full_body/core_and_carry/custom/…), not a
# safety-relevant enum.
VALID_FEEDBACK = {"liked", "disliked", "rejected"}


class WorkoutCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workout_type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    is_template: bool = False


class WorkoutUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    workout_type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    is_template: bool | None = None


class ExerciseAdd(BaseModel):
    exercise_id: str
    sets: int = Field(default=3, ge=1, le=20)
    reps: str | None = Field(default=None, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=1, le=7200)
    rest_seconds: int = Field(default=60, ge=0, le=1200)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    notes: str | None = None
    position: int | None = Field(default=None, ge=0, description="Insert index; appends if omitted")

    @model_validator(mode="after")
    def _need_reps_or_duration(self) -> "ExerciseAdd":
        if not self.reps and self.duration_seconds is None:
            raise ValueError("Provide reps or duration_seconds (or both).")
        return self


class ExerciseUpdate(BaseModel):
    sets: int | None = Field(default=None, ge=1, le=20)
    reps: str | None = Field(default=None, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=1, le=7200)
    rest_seconds: int | None = Field(default=None, ge=0, le=1200)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    notes: str | None = None


class ReorderRequest(BaseModel):
    exercise_ids: list[int] = Field(min_length=1, description="WorkoutExercise ids in the desired order")


class ExercisePerformance(BaseModel):
    workout_exercise_id: int
    feedback: str | None = None  # liked | disliked | rejected
    rejection_reason: str | None = Field(
        default=None,
        description="Only used when feedback='rejected' — becomes a RejectionEvent reason "
        "(dont_like, too_hard, too_sore, …). Defaults to 'dont_like'.",
    )

    @model_validator(mode="after")
    def _check_feedback(self) -> "ExercisePerformance":
        if self.feedback and self.feedback not in VALID_FEEDBACK:
            raise ValueError(f"feedback must be one of {sorted(VALID_FEEDBACK)}")
        return self


class CompleteWorkoutRequest(BaseModel):
    performances: list[ExercisePerformance] = Field(default_factory=list)


# ── Response models ──────────────────────────────────────────────────────────

class MuscleCoverage(BaseModel):
    muscle: str
    display_name: str
    activation: float  # 0-1, summed across the workout then normalised to the max


class WorkoutAnalysis(BaseModel):
    exercise_count: int
    estimated_minutes: int
    target_minutes: int | None
    duration_verdict: str  # "short" | "on_target" | "long" | "unknown"
    muscle_coverage: list[MuscleCoverage]
    pattern_breakdown: dict[str, int]
    missing_patterns: list[str]
    injury_conflicts: list[str]
    warnings: list[str]


class SuggestionItem(BaseModel):
    exercise: dict
    mechanic: str
    already_added: bool
    suggestibility_state: str
    suggestibility_reason: str | None = None


class SuggestionResponse(BaseModel):
    workout_id: int
    workout_type: str | None
    total: int
    offset: int
    suggestions: list[SuggestionItem]
    facets: dict[str, dict[str, int]] | None = None


class WorkoutMutationResponse(BaseModel):
    workout: WorkoutLogOut
    warnings: list[str] = []


__all__ = [
    "WorkoutCreate", "WorkoutUpdate", "ExerciseAdd", "ExerciseUpdate",
    "ReorderRequest", "ExercisePerformance", "CompleteWorkoutRequest",
    "WorkoutAnalysis", "MuscleCoverage", "SuggestionItem", "SuggestionResponse",
    "WorkoutMutationResponse", "WorkoutExerciseOut", "WorkoutLogOut",
]
