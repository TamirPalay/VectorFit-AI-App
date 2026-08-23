"""
RejectionEvent ORM model.

Every time a user rejects an exercise (for any reason), we store a structured
event here. The suggestibility engine reads these events at suggestion-time to
compute current eligibility — nothing is pre-cached so state is never stale.

Reason taxonomy (maps directly to the UI rejection flow):
  dont_like       → lowers preference score; exercise resurfaces occasionally
  hurts           → triggers injury suppression (needs pain_type + body_area)
  not_enough_time → short cooldown (1-2 days)
  no_equipment    → no cooldown; equipment-filtered going forward
  too_easy        → preference penalty
  too_hard        → preference penalty
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


REJECTION_REASONS = {
    # Cooldown triggers (temporary, auto-clear)
    "too_sore",       # 3-day cooldown — muscle soreness
    "too_tired",      # 2-day cooldown — general fatigue
    "not_today",      # 1-day soft skip — no lasting effect
    # Preference penalties (permanent but gradual)
    "dont_like",      # -0.15 — general dislike
    "too_easy",       # -0.10 — needs progression
    "too_hard",       # -0.10 — needs regression
    "too_long",       # -0.05 — time constraint
    "bad_form",       # -0.08 — not confident in technique
    "no_equipment",   # -0.05 — missing kit
    # Catch-all
    "other",
}

PAIN_TYPES = {
    "sharp_acute",   # → SUPPRESSED state in suggestibility engine
    "dull_stiff",    # → COOLDOWN state (shorter duration)
    "old_recurring", # → SUPPRESSED (tied to injury model)
    "new_unsure",    # → SUPPRESSED (treated cautiously)
}


class RejectionEvent(Base):
    __tablename__ = "rejection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    exercise_id: Mapped[str] = mapped_column(String(100), index=True)
    exercise_name: Mapped[str] = mapped_column(String(200))

    reason: Mapped[str] = mapped_column(String(30))
    # One of REJECTION_REASONS

    # ── Populated only when reason == "hurts" ─────────────────────────────────
    pain_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 1 (mild) – 5 (severe)

    pain_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # One of PAIN_TYPES

    body_area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Free-text body area (e.g. "right shoulder", "lower back")

    recovery_expectation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How many days until the user expects this to resolve

    # ── Optional free-text note (shown last in the rejection flow UI) ─────────
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return (
            f"<RejectionEvent id={self.id} exercise={self.exercise_id!r} "
            f"reason={self.reason!r}>"
        )
