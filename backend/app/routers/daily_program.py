from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.workout import DayProgramOut, WeekProgramOut, WorkoutLogOut
from app.services.daily_program_engine import WORKOUT_TYPES, DailyProgramEngine

router = APIRouter(prefix="/users/{user_id}", tags=["daily-program"])


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _find_log(db: Session, user_id: int, d: date) -> WorkoutLog | None:
    start, end = _day_bounds(d)
    return (
        db.query(WorkoutLog)
        .filter(
            WorkoutLog.user_id == user_id,
            WorkoutLog.source == "daily",
            WorkoutLog.started_at >= start,
            WorkoutLog.started_at < end,
        )
        .first()
    )


def _to_out(log: WorkoutLog) -> WorkoutLogOut:
    out = WorkoutLogOut.model_validate(log)
    out.workout_label = WORKOUT_TYPES.get(log.workout_type, {}).get("label")
    return out


@router.post("/daily-program", response_model=DayProgramOut)
async def generate_daily_program(
    user_id: int,
    force: bool = False,
    train: bool = False,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Generate (or return today's already-generated) daily program.

    force=true deletes today's plan and regenerates it from scratch.
    train=true additionally overrides a scheduled rest day — the user tapped
    "train anyway", so build a workout even though the weekly quota is met.
    Any exercise blocked by an active injury/cooldown is still swapped
    automatically, with the reason recorded on that exercise for the UI tooltip.
    """
    user = _get_user_or_404(user_id, db)
    today = datetime.now(timezone.utc).date()

    existing = _find_log(db, user_id, today)
    if existing and not force and not train:
        return DayProgramOut(day_index=0, date=today, is_rest=False, workout=_to_out(existing))
    if existing and (force or train):
        db.delete(existing)
        db.commit()

    engine = DailyProgramEngine(db=db, index=request.app.state.exercise_index)
    day = await engine.generate_day(user, today, day_index=0, allow_rest=not train)
    log = engine.persist_day(user, day)

    return DayProgramOut(
        day_index=0, date=today, is_rest=day.is_rest,
        workout=_to_out(log) if log else None,
        warnings=day.warnings,
    )


@router.get("/daily-program/today", response_model=DayProgramOut)
def get_today_program(user_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    today = datetime.now(timezone.utc).date()
    log = _find_log(db, user_id, today)
    if not log:
        raise HTTPException(404, "No program generated for today yet — POST /daily-program first")
    return DayProgramOut(day_index=0, date=today, is_rest=False, workout=_to_out(log))


@router.post("/weekly-program", response_model=WeekProgramOut)
async def generate_weekly_program(
    user_id: int,
    force: bool = False,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Generate the next 7 days (rolling from today, not calendar-aligned).
    Rest days and workout types are chosen together so the week reads as one
    program — not a fixed rotation replayed 7 times.
    """
    user = _get_user_or_404(user_id, db)
    today = datetime.now(timezone.utc).date()

    if force:
        # Re-plan only the days that haven't happened yet — never throw away a
        # workout the user already completed.
        for i in range(7):
            existing = _find_log(db, user_id, today + timedelta(days=i))
            if existing and existing.completed_at is None:
                db.delete(existing)
        db.commit()
    else:
        # Already planned this rolling window? Return it as-is — don't re-run
        # the engine just to rebuild the same week. "Planned" means there's a
        # log for a *future* day; a lone log for today (from the Today screen)
        # doesn't count, so the first weekly generation still runs.
        existing_logs = {i: _find_log(db, user_id, today + timedelta(days=i)) for i in range(7)}
        if any(existing_logs[i] for i in range(1, 7)):
            return WeekProgramOut(days=[
                DayProgramOut(
                    day_index=i, date=today + timedelta(days=i),
                    is_rest=log is None, workout=_to_out(log) if log else None,
                )
                for i, log in existing_logs.items()
            ])

    engine = DailyProgramEngine(db=db, index=request.app.state.exercise_index)
    day_plans = await engine.generate_week(user, today)

    out_days = []
    for day in day_plans:
        existing = _find_log(db, user_id, day.date)  # a completed log survived the force-delete
        if existing is not None:
            out_days.append(DayProgramOut(
                day_index=day.day_index, date=day.date, is_rest=False, workout=_to_out(existing),
            ))
            continue
        log = engine.persist_day(user, day)
        out_days.append(DayProgramOut(
            day_index=day.day_index, date=day.date, is_rest=day.is_rest,
            workout=_to_out(log) if log else None,
            warnings=day.warnings,
        ))

    return WeekProgramOut(days=out_days)


@router.get("/weekly-program", response_model=WeekProgramOut)
def get_weekly_program(user_id: int, db: Session = Depends(get_db)):
    """Fetch the already-generated next 7 days (rolling from today). Days with
    no persisted log are returned as rest days — either genuinely scheduled
    rest, or simply not generated yet."""
    _get_user_or_404(user_id, db)
    today = datetime.now(timezone.utc).date()

    out_days = []
    for i in range(7):
        d = today + timedelta(days=i)
        log = _find_log(db, user_id, d)
        out_days.append(DayProgramOut(
            day_index=i, date=d, is_rest=log is None,
            workout=_to_out(log) if log else None,
        ))
    return WeekProgramOut(days=out_days)
