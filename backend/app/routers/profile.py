"""
Profile router: full CRUD for users and their injuries.

Endpoints:
  POST   /users                         Create user
  GET    /users/{user_id}               Get user + injuries
  PATCH  /users/{user_id}               Update user fields
  DELETE /users/{user_id}               Delete user

  POST   /users/{user_id}/injuries      Add injury
  PATCH  /users/{user_id}/injuries/{id} Update injury details
  DELETE /users/{user_id}/injuries/{id} Remove injury
  POST   /users/{user_id}/injuries/{id}/heal  Mark injury healed (takes effect immediately)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_metric import DailyMetric
from app.models.rejection import RejectionEvent
from app.models.user import Injury, User
from app.models.workout_log import WorkoutLog
from app.schemas.user import InjuryCreate, InjuryOut, InjuryUpdate, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["profile"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _get_injury_or_404(user_id: int, injury_id: int, db: Session) -> Injury:
    injury = db.get(Injury, injury_id)
    if not injury or injury.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Injury not found")
    return injury


def _apply_user_update(user: User, data: UserUpdate) -> User:
    """Apply only the fields that were actually provided (partial update)."""
    update = data.model_dump(exclude_unset=True)
    for field, value in update.items():
        # List fields map to ORM properties that internally serialize to JSON
        setattr(user, field, value)
    return user


# ── User CRUD ─────────────────────────────────────────────────────────────────

@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserOut:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered",
        )
    user = User(
        name=payload.name,
        email=payload.email,
        age=payload.age,
        weight_kg=payload.weight_kg,
        height_cm=payload.height_cm,
        fitness_level=payload.fitness_level,
        experience_level=payload.experience_level,
        days_per_week=payload.days_per_week,
        minutes_per_session=payload.minutes_per_session,
        show_personal_records=payload.show_personal_records,
    )
    user.goals = payload.goals
    user.equipment = payload.equipment
    user.movement_preferences = payload.movement_preferences

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), limit: int = 100) -> list[UserOut]:
    """Every profile, newest first — powers the profile picker / switcher so a
    freshly created profile shows up alongside the demo users."""
    users = db.query(User).order_by(User.id.asc()).limit(limit).all()
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserOut:
    user = _get_user_or_404(user_id, db)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> UserOut:
    user = _get_user_or_404(user_id, db)
    _apply_user_update(user, payload)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a profile and everything attached to it. FK constraints aren't
    enforced on the dev SQLite file, so related rows are removed explicitly to
    avoid orphans (workout logs cascade to their exercises via the ORM
    relationship; injuries cascade via the User relationship)."""
    user = _get_user_or_404(user_id, db)
    db.query(RejectionEvent).filter(RejectionEvent.user_id == user_id).delete(synchronize_session=False)
    db.query(DailyMetric).filter(DailyMetric.user_id == user_id).delete(synchronize_session=False)
    for log in db.query(WorkoutLog).filter(WorkoutLog.user_id == user_id).all():
        db.delete(log)
    db.delete(user)
    db.commit()


# ── Injury CRUD ───────────────────────────────────────────────────────────────

@router.post("/{user_id}/injuries", response_model=InjuryOut, status_code=status.HTTP_201_CREATED)
def add_injury(user_id: int, payload: InjuryCreate, db: Session = Depends(get_db)) -> InjuryOut:
    _get_user_or_404(user_id, db)  # ensures user exists
    injury = Injury(
        user_id=user_id,
        body_part=payload.body_part,
        severity=payload.severity,
        pain_type=payload.pain_type,
        recovery_expectation_days=payload.recovery_expectation_days,
        notes=payload.notes,
        is_active=True,
    )
    db.add(injury)
    db.commit()
    db.refresh(injury)
    return InjuryOut.model_validate(injury)


@router.patch("/{user_id}/injuries/{injury_id}", response_model=InjuryOut)
def update_injury(
    user_id: int, injury_id: int, payload: InjuryUpdate, db: Session = Depends(get_db)
) -> InjuryOut:
    injury = _get_injury_or_404(user_id, injury_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(injury, field, value)
    db.commit()
    db.refresh(injury)
    return InjuryOut.model_validate(injury)


@router.post("/{user_id}/injuries/{injury_id}/heal", response_model=InjuryOut)
def heal_injury(user_id: int, injury_id: int, db: Session = Depends(get_db)) -> InjuryOut:
    """
    Mark an injury as healed. Takes effect immediately — the suggestibility
    engine reads healed_at at suggestion-time, so no separate reset is needed.
    """
    injury = _get_injury_or_404(user_id, injury_id, db)
    injury.healed_at = datetime.now(timezone.utc)
    injury.is_active = False
    db.commit()
    db.refresh(injury)
    return InjuryOut.model_validate(injury)


@router.delete("/{user_id}/injuries/{injury_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_injury(user_id: int, injury_id: int, db: Session = Depends(get_db)) -> None:
    injury = _get_injury_or_404(user_id, injury_id, db)
    db.delete(injury)
    db.commit()
