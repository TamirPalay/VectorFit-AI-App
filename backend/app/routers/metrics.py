"""
Daily health metrics — Stage 9.

Manual entry / edit of the non-workout signals the dashboard charts (steps,
calories, body weight, sleep, resting HR, energy). One row per (user, date);
PUT is an upsert.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_metric import DailyMetric
from app.models.user import User
from app.schemas.metric import MetricOut, MetricUpsert

router = APIRouter(prefix="/users/{user_id}/metrics", tags=["metrics"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.get("", response_model=list[MetricOut])
def list_metrics(
    user_id: int,
    db: Session = Depends(get_db),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
):
    _get_user_or_404(user_id, db)
    to = date_to or datetime.now(timezone.utc).date()
    frm = date_from or (to - timedelta(days=30))
    rows = (
        db.query(DailyMetric)
        .filter(DailyMetric.user_id == user_id, DailyMetric.date >= frm, DailyMetric.date <= to)
        .order_by(DailyMetric.date)
        .all()
    )
    return [MetricOut.model_validate(r) for r in rows]


@router.get("/{day}", response_model=MetricOut)
def get_metric(user_id: int, day: date, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    row = db.query(DailyMetric).filter(DailyMetric.user_id == user_id, DailyMetric.date == day).first()
    if not row:
        raise HTTPException(404, f"No metrics recorded for {day}")
    return MetricOut.model_validate(row)


@router.put("/{day}", response_model=MetricOut)
def upsert_metric(user_id: int, day: date, body: MetricUpsert, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    row = db.query(DailyMetric).filter(DailyMetric.user_id == user_id, DailyMetric.date == day).first()
    if row is None:
        row = DailyMetric(user_id=user_id, date=day)
        db.add(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return MetricOut.model_validate(row)


@router.delete("/{day}", status_code=204)
def delete_metric(user_id: int, day: date, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    row = db.query(DailyMetric).filter(DailyMetric.user_id == user_id, DailyMetric.date == day).first()
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)
