"""
DailyMetric ORM model — Stage 9 (dashboard).

One row per (user, calendar date). Holds the non-workout health signals the
dashboard charts: steps, calories, body weight, sleep, resting HR, and a
subjective energy rating. In a shipped app these would sync from Apple Health /
Google Fit; here they're entered via PUT /users/{id}/metrics/{date} and the
demo seeder populates a couple of months of history.
"""

from datetime import date as _date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_metric_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)

    date: Mapped[_date] = mapped_column(Date, index=True)

    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resting_heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 (drained) – 5 (great)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship("User")  # noqa: F821

    def __repr__(self) -> str:
        return f"<DailyMetric user_id={self.user_id} date={self.date} steps={self.steps}>"
