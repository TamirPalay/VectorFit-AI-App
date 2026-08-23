from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator

REJECTION_REASONS = {"too_sore", "too_tired", "dont_like", "too_easy", "too_hard", "no_equipment", "other"}


class RejectionCreate(BaseModel):
    exercise_id: str
    reason: str
    pain_level: Optional[int] = None
    pain_type: Optional[str] = None
    body_area: Optional[str] = None
    recovery_expectation: Optional[int] = None
    note: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def reason_must_be_valid(cls, v: str) -> str:
        if v not in REJECTION_REASONS:
            raise ValueError(f"reason must be one of {sorted(REJECTION_REASONS)}")
        return v

    @field_validator("pain_level")
    @classmethod
    def pain_level_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 10):
            raise ValueError("pain_level must be 1–10")
        return v

    model_config = {"from_attributes": True}


class RejectionOut(RejectionCreate):
    id: int
    user_id: int
    created_at: datetime
