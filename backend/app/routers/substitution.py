from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.substitution_engine import SubstitutionEngine, Substitute

router = APIRouter(prefix="/users/{user_id}", tags=["substitution"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _sub_to_dict(s: Substitute) -> dict:
    return {
        "exercise": s.exercise,
        "similarity": s.similarity,
        "coverage": s.coverage,
        "preference_score": s.preference_score,
        "rank_score": s.rank_score,
    }


@router.get("/substitute/{exercise_id}")
def get_substitutes(
    user_id: int,
    exercise_id: str,
    top_k: int = 5,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Return the top substitutes for a suppressed or unwanted exercise.
    Results are ordered by similarity × preference_score.
    """
    _get_user_or_404(user_id, db)
    index = request.app.state.exercise_index
    engine = SubstitutionEngine(db=db, index=index)
    try:
        substitutes = engine.find_substitutes(user_id, exercise_id, top_k=top_k)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return [_sub_to_dict(s) for s in substitutes]
