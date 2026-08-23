from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.substitution_engine import SubstitutionEngine, COMPLEMENT_COVERAGE_THRESHOLD
from app.services.suggestibility_engine import SuggestibilityEngine
from app.services.explanation_service import explain_substitution_set

router = APIRouter(prefix="/users/{user_id}", tags=["explanation"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.get("/explain/{exercise_id}")
async def explain_substitutes(
    user_id: int,
    exercise_id: str,
    top_k: int = 3,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Find safe substitutes for a suppressed exercise and explain each one
    in plain English via the LLM.

    Returns up to top_k substitutes, each with similarity, coverage, and
    a 2-3 sentence natural-language explanation.
    """
    _get_user_or_404(user_id, db)
    index = request.app.state.exercise_index

    original = index.get_by_id(exercise_id)
    if original is None:
        raise HTTPException(404, f"Exercise '{exercise_id}' not found")

    # Get the suggestibility result for the original (for suppression context)
    sg_engine = SuggestibilityEngine(db)
    sg_result = sg_engine.compute(user_id, original)

    # Find substitutes
    sub_engine = SubstitutionEngine(db=db, index=index)
    try:
        substitutes = sub_engine.find_substitutes(user_id, exercise_id, top_k=top_k)
    except ValueError as e:
        raise HTTPException(404, str(e))

    if not substitutes:
        return {
            "original": original,
            "suggestibility": {
                "state": sg_result.state.value,
                "reason": sg_result.suppression_reason,
            },
            "substitutes": [],
            "message": (
                "No safe substitutes found. The injury restrictions may block all "
                "similar exercises. Consider consulting a physiotherapist."
            ),
        }

    # For substitutes with coverage below threshold, find complementary exercises
    complements_per_sub: dict[str, list[dict]] = {}
    for sub in substitutes:
        if sub.coverage < COMPLEMENT_COVERAGE_THRESHOLD:
            complements = sub_engine.find_complements(
                user_id=user_id,
                target_id=exercise_id,
                substitute_id=sub.exercise["id"],
                top_k=4,
            )
            if complements:
                complements_per_sub[sub.exercise["id"]] = complements

    explained = await explain_substitution_set(
        original, substitutes, sg_result, complements_per_sub
    )

    return {
        "original": original,
        "suggestibility": {
            "state": sg_result.state.value,
            "reason": sg_result.suppression_reason,
        },
        "substitutes": explained,
    }
