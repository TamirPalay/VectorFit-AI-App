"""
User and Injury ORM models.

Design notes:
- Injuries are their own table (one user : many injuries) so they can be
  individually healed, deleted, or added without touching the user row.
- Equipment and goals are stored as JSON arrays in SQLite TEXT columns — simple
  enough that a junction table would be overkill at this scale.
- movement_preferences is also a JSON list (e.g. ["free_weights", "cables"]).
"""

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Physical attributes
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Fitness context
    # Stored as JSON strings: e.g. '["barbell", "dumbbells"]'
    goals_json: Mapped[str] = mapped_column(Text, default="[]")
    equipment_json: Mapped[str] = mapped_column(Text, default="[]")
    movement_preferences_json: Mapped[str] = mapped_column(Text, default="[]")

    fitness_level: Mapped[str] = mapped_column(String(20), default="beginner")
    # "beginner" | "intermediate" | "advanced"

    experience_level: Mapped[str] = mapped_column(String(20), default="beginner")
    # could be different from fitness_level (e.g. advanced knowledge, low fitness)

    days_per_week: Mapped[int] = mapped_column(Integer, default=3)
    minutes_per_session: Mapped[int] = mapped_column(Integer, default=45)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Relationships
    injuries: Mapped[list["Injury"]] = relationship(
        "Injury", back_populates="user", cascade="all, delete-orphan"
    )

    # ── JSON helpers ──────────────────────────────────────────────────────────

    @property
    def goals(self) -> list[str]:
        return json.loads(self.goals_json)

    @goals.setter
    def goals(self, value: list[str]) -> None:
        self.goals_json = json.dumps(value)

    @property
    def equipment(self) -> list[str]:
        return json.loads(self.equipment_json)

    @equipment.setter
    def equipment(self, value: list[str]) -> None:
        self.equipment_json = json.dumps(value)

    @property
    def movement_preferences(self) -> list[str]:
        return json.loads(self.movement_preferences_json)

    @movement_preferences.setter
    def movement_preferences(self, value: list[str]) -> None:
        self.movement_preferences_json = json.dumps(value)

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.name!r}>"


class Injury(Base):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    body_part: Mapped[str] = mapped_column(String(100))
    # e.g. "right shoulder", "left knee", "lower back"

    severity: Mapped[str] = mapped_column(String(20), default="moderate")
    # "mild" | "moderate" | "severe"

    pain_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "sharp_acute" | "dull_stiff" | "old_recurring" | "new_unsure"

    recovery_expectation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How many days from created_at until the user expects to recover.
    # None = unknown / indefinite.

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When set, the injury is considered healed and no longer affects suggestions.
    healed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Soft flag: False once healed_at is set. Used for quick DB filtering.

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship("User", back_populates="injuries")

    @property
    def is_healed(self) -> bool:
        return self.healed_at is not None

    @property
    def expected_recovery_date(self) -> datetime | None:
        if self.recovery_expectation_days is None:
            return None
        from datetime import timedelta
        return self.created_at + timedelta(days=self.recovery_expectation_days)

    def __repr__(self) -> str:
        return f"<Injury id={self.id} body_part={self.body_part!r} active={self.is_active}>"
