"""
Workout log history — Stage 9.

Cross-source read + completion for every WorkoutLog (generated daily programs
and custom-builder sessions alike). The custom-builder router still owns
building/editing; this one owns "show me my history" and "mark it done".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.data.muscles import MUSCLES
from app.database import get_db
from app.models.rejection import REJECTION_REASONS, RejectionEvent
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.custom_workout import CompleteWorkoutRequest
from app.schemas.workout import WorkoutLogOut
from app.services.daily_program_engine import WORKOUT_TYPES

router = APIRouter(prefix="/users/{user_id}/workout-logs", tags=["workout-history"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


_SOFT_DISLIKE_NOTE = "soft-dislike"


def _record_soft_dislike(db: Session, user_id: int, exercise_id: str, exercise_name: str) -> None:
    """A 👎 (disliked) is a soft "fewer of these" signal — recorded as a
    `dont_like` RejectionEvent so the suggestibility engine's preference score
    picks it up (-0.15, still eligible), NOT a hard ✕ rejection. Tagged with a
    marker note so the UI can list it under "You disliked" rather than
    "Won't be suggested". Idempotent per exercise."""
    exists = (
        db.query(RejectionEvent)
        .filter(
            RejectionEvent.user_id == user_id,
            RejectionEvent.exercise_id == exercise_id,
            RejectionEvent.note == _SOFT_DISLIKE_NOTE,
        )
        .first()
    )
    if exists is None:
        db.add(RejectionEvent(
            user_id=user_id, exercise_id=exercise_id, exercise_name=exercise_name,
            reason="dont_like", note=_SOFT_DISLIKE_NOTE, created_at=datetime.now(timezone.utc),
        ))


def _get_log_or_404(user_id: int, log_id: int, db: Session) -> WorkoutLog:
    log = db.query(WorkoutLog).filter(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id).first()
    if not log:
        raise HTTPException(404, "Workout log not found")
    return log


def _out(log: WorkoutLog) -> WorkoutLogOut:
    data = WorkoutLogOut.model_validate(log)
    if log.workout_type:
        data.workout_label = WORKOUT_TYPES.get(log.workout_type, {}).get("label")
    return data


def _summary_row(log: WorkoutLog, index) -> dict:
    top_muscles: dict[str, float] = {}
    patterns: dict[str, int] = {}
    for we in log.exercises:
        ex = index.get_by_id(we.exercise_id)
        if not ex:
            continue
        patterns[ex["movement_pattern"]] = patterns.get(ex["movement_pattern"], 0) + 1
        for m, v in ex["muscle_activation"].items():
            if m in MUSCLES:
                top_muscles[m] = top_muscles.get(m, 0.0) + v * we.sets
    top = sorted(top_muscles.items(), key=lambda kv: -kv[1])[:3]
    return {
        "id": log.id,
        "name": log.name,
        "date": log.started_at.date().isoformat(),
        "source": log.source,
        "workout_type": log.workout_type,
        "workout_label": WORKOUT_TYPES.get(log.workout_type, {}).get("label"),
        "completed": log.completed_at is not None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "exercise_count": len(log.exercises),
        "total_sets": sum(we.sets for we in log.exercises),
        "swap_count": sum(1 for we in log.exercises if we.substituted_for_id),
        "top_muscles": [m for m, _ in top],
        "pattern_mix": dict(sorted(patterns.items(), key=lambda kv: -kv[1])),
    }


@router.get("")
def list_logs(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    source: str | None = Query(None, description="daily | custom_builder"),
    status: str = Query("all", pattern="^(all|completed|planned)$"),
    include_templates: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _get_user_or_404(user_id, db)
    index = request.app.state.exercise_index
    to = date_to or datetime.now(timezone.utc).date()
    frm = date_from or (to - timedelta(days=90))
    start_dt = datetime.combine(frm, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    q = db.query(WorkoutLog).filter(
        WorkoutLog.user_id == user_id,
        WorkoutLog.started_at >= start_dt, WorkoutLog.started_at < end_dt,
    )
    if not include_templates:
        q = q.filter(WorkoutLog.is_template.is_(False))
    if source:
        q = q.filter(WorkoutLog.source == source)
    if status == "completed":
        q = q.filter(WorkoutLog.completed_at.isnot(None))
    elif status == "planned":
        q = q.filter(WorkoutLog.completed_at.is_(None))

    total = q.count()
    logs = q.order_by(WorkoutLog.started_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "offset": offset, "logs": [_summary_row(x, index) for x in logs]}


@router.get("/{log_id}", response_model=WorkoutLogOut)
def get_log(user_id: int, log_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    return _out(_get_log_or_404(user_id, log_id, db))


@router.post("/{log_id}/complete", response_model=WorkoutLogOut)
def complete_log(
    user_id: int, log_id: int, body: CompleteWorkoutRequest | None = None,
    db: Session = Depends(get_db),
):
    """Mark any workout (daily program or custom session) done. Optional
    per-exercise feedback; a 'rejected' mark becomes a RejectionEvent."""
    _get_user_or_404(user_id, db)
    log = _get_log_or_404(user_id, log_id, db)
    if log.is_template:
        raise HTTPException(400, "Templates can't be completed — start a session from it first.")

    log.completed_at = datetime.now(timezone.utc)
    if body and body.performances:
        by_id = {we.id: we for we in log.exercises}
        for perf in body.performances:
            we = by_id.get(perf.workout_exercise_id)
            if we is None:
                raise HTTPException(404, f"workout_exercise_id {perf.workout_exercise_id} not in this workout")
            we.feedback = perf.feedback
            if perf.feedback == "rejected":
                reason = perf.rejection_reason if perf.rejection_reason in REJECTION_REASONS else "dont_like"
                db.add(RejectionEvent(
                    user_id=user_id, exercise_id=we.exercise_id, exercise_name=we.exercise_name,
                    reason=reason, note="Auto-logged from workout completion",
                    created_at=datetime.now(timezone.utc),
                ))
            elif perf.feedback == "disliked":
                _record_soft_dislike(db, user_id, we.exercise_id, we.exercise_name)
    db.commit()
    db.refresh(log)
    return _out(log)


@router.post("/{log_id}/reopen", response_model=WorkoutLogOut)
def reopen_log(user_id: int, log_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = _get_log_or_404(user_id, log_id, db)
    log.completed_at = None
    db.commit()
    db.refresh(log)
    return _out(log)


@router.delete("/{log_id}", status_code=204)
def delete_log(user_id: int, log_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = _get_log_or_404(user_id, log_id, db)
    db.delete(log)
    db.commit()
    return Response(status_code=204)
