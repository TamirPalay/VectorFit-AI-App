from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rejection import RejectionEvent
from app.models.user import User
from app.schemas.rejection import RejectionCreate, RejectionOut
from app.services.suggestibility_engine import SuggestibilityEngine, SuggestibilityResult

router = APIRouter(prefix="/users/{user_id}", tags=["suggestibility"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _load_exercises(request) -> dict:
    index = request.app.state.exercise_index
    return {ex["id"]: ex for ex in index.exercises}


def _result_to_dict(r: SuggestibilityResult) -> dict:
    return {
        "exercise_id": r.exercise_id,
        "state": r.state.value,
        "preference_score": r.preference_score,
        "suppressed_until": r.suppressed_until.isoformat() if r.suppressed_until else None,
        "cooldown_until": r.cooldown_until.isoformat() if r.cooldown_until else None,
        "suppression_reason": r.suppression_reason,
        "blocked_flags": sorted(r.blocked_flags),
    }


# ── Log a rejection ──────────────────────────────────────────────────────────

@router.post("/rejections", response_model=RejectionOut, status_code=201)
def log_rejection(
    user_id: int,
    body: RejectionCreate,
    request: Request = None,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    index = request.app.state.exercise_index
    ex = index.get_by_id(body.exercise_id)
    if ex is None:
        raise HTTPException(404, f"Exercise '{body.exercise_id}' not found")
    event = RejectionEvent(
        user_id=user_id,
        exercise_id=body.exercise_id,
        exercise_name=ex["name"],
        reason=body.reason,
        pain_level=body.pain_level,
        pain_type=body.pain_type,
        body_area=body.body_area,
        recovery_expectation_days=body.recovery_expectation,
        note=body.note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/rejections")
def list_rejections(user_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    rows = (
        db.query(RejectionEvent)
        .filter(RejectionEvent.user_id == user_id)
        .order_by(RejectionEvent.created_at.desc())
        .all()
    )
    return rows


@router.delete("/rejections/{rejection_id}", status_code=204)
def delete_rejection(user_id: int, rejection_id: int, db: Session = Depends(get_db)):
    """Undo a rejection — the exercise becomes eligible again on the next
    suggestion (nothing is cached)."""
    _get_user_or_404(user_id, db)
    row = (
        db.query(RejectionEvent)
        .filter(RejectionEvent.id == rejection_id, RejectionEvent.user_id == user_id)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


# ── Single exercise suggestibility ───────────────────────────────────────────

@router.get("/suggestibility/{exercise_id}")
def get_suggestibility(
    user_id: int,
    exercise_id: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    exercises = _load_exercises(request)
    if exercise_id not in exercises:
        raise HTTPException(404, f"Exercise '{exercise_id}' not found")
    engine = SuggestibilityEngine(db)
    result = engine.compute(user_id, exercises[exercise_id])
    return _result_to_dict(result)


# ── Batch suggestibility ──────────────────────────────────────────────────────

class BatchRequest(BaseModel):
    exercise_ids: list[str]


@router.post("/suggestibility/batch")
def batch_suggestibility(
    user_id: int,
    body: BatchRequest,
    request: Request = None,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    all_ex = _load_exercises(request)
    exercises = [all_ex[eid] for eid in body.exercise_ids if eid in all_ex]
    engine = SuggestibilityEngine(db)
    results = engine.batch_compute(user_id, exercises)
    return [_result_to_dict(r) for r in results]
