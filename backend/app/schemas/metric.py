"""Pydantic schemas for daily health metrics (Stage 9)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class MetricUpsert(BaseModel):
    """Body for PUT /users/{id}/metrics/{date}. All fields optional — send only
    what you're recording; omitted fields are left untouched, explicit null
    clears a value."""

    steps: int | None = Field(default=None, ge=0, le=200_000)
    active_calories: int | None = Field(default=None, ge=0, le=20_000)
    resting_heart_rate: int | None = Field(default=None, ge=20, le=200)
    body_weight_kg: float | None = Field(default=None, ge=20, le=400)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    energy_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _not_empty(self) -> "MetricUpsert":
        if not self.model_fields_set:
            raise ValueError("Provide at least one metric field.")
        return self


class MetricOut(BaseModel):
    date: date
    steps: int | None = None
    active_calories: int | None = None
    resting_heart_rate: int | None = None
    body_weight_kg: float | None = None
    sleep_hours: float | None = None
    energy_level: int | None = None
    notes: str | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
