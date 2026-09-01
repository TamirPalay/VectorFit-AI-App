"""
Custom workout builder — Stage 8.

A custom workout is a WorkoutLog with source="custom_builder" and a user-given
name. It can be a one-off (is_template=False) or a reusable blueprint
(is_template=True); starting a template clones it into a fresh session log.

Everything here is deterministic — no LLM calls. Injuries never hard-block a
pick: adding a suppressed exercise succeeds with a warning + substitute
suggestions, consistent with the Stage 4 design.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.data.muscles import MOVEMENT_PATTERNS, MUSCLE_DISPLAY, MUSCLES
from app.database import get_db
from app.models.rejection import REJECTION_REASONS, RejectionEvent
from app.models.user import User
from app.models.workout_log import WorkoutExercise, WorkoutLog
from app.schemas.custom_workout import (
    CompleteWorkoutRequest,
    ExerciseAdd,
    ExerciseUpdate,
    MuscleCoverage,
    ReorderRequest,
    SuggestionItem,
    SuggestionResponse,
    WorkoutAnalysis,
    WorkoutCreate,
    WorkoutMutationResponse,
    WorkoutUpdate,
)
from app.routers.workout_logs import _record_soft_dislike
from app.schemas.workout import WorkoutLogOut
from app.services.daily_program_engine import WORKOUT_TYPES
from app.services.exercise_filters import ExerciseQuery, apply_filters, compute_facets, mechanic_of
from app.services.substitution_engine import SubstitutionEngine
from app.services.suggestibility_engine import SuggestibilityEngine, SuggestibilityState

router = APIRouter(prefix="/users/{user_id}/workouts", tags=["custom-workout"])

_SOURCE = "custom_builder"
_BLOCKED = (SuggestibilityState.SUPPRESSED, SuggestibilityState.COOLDOWN)

# Focus options for the builder — a superset of the daily engine's schedulable
# WORKOUT_TYPES. Each maps to the movement patterns that scope the suggested
# list; body-part focuses lean on those patterns plus the picker's body-part
# chips. label + patterns; [] patterns = "suggest from everything".
BUILDER_FOCUS: dict[str, dict] = {
    "full_body":      {"label": "Full Body",       "patterns": ["push", "pull", "squat", "hinge"]},
    "upper":          {"label": "Upper Body",      "patterns": ["push", "pull"]},
    "lower":          {"label": "Lower Body",      "patterns": ["squat", "hinge"]},
    "push":           {"label": "Push",            "patterns": ["push"]},
    "pull":           {"label": "Pull",            "patterns": ["pull"]},
    "legs":           {"label": "Legs",            "patterns": ["squat", "hinge"]},
    "chest":          {"label": "Chest",           "patterns": ["push"]},
    "back":           {"label": "Back",            "patterns": ["pull"]},
    "shoulders":      {"label": "Shoulders",       "patterns": ["push"]},
    "arms":           {"label": "Arms",            "patterns": ["push", "pull"]},
    "glutes":         {"label": "Glutes",          "patterns": ["hinge", "squat"]},
    "core":           {"label": "Core",            "patterns": ["core"]},
    "core_and_carry": {"label": "Core & Carry",    "patterns": ["core", "carry"]},
    "conditioning":   {"label": "Conditioning",    "patterns": ["core", "carry"]},
    "mobility":       {"label": "Mobility",        "patterns": ["core"]},
    "custom":         {"label": "Custom",          "patterns": []},
}
CUSTOM_WORKOUT_TYPES = list(BUILDER_FOCUS)


def _focus(workout_type: str | None) -> dict:
    return BUILDER_FOCUS.get(workout_type or "", WORKOUT_TYPES.get(workout_type or "", {}))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _get_workout_or_404(user_id: int, workout_id: int, db: Session) -> WorkoutLog:
    log = (
        db.query(WorkoutLog)
        .filter(WorkoutLog.id == workout_id, WorkoutLog.user_id == user_id, WorkoutLog.source == _SOURCE)
        .first()
    )
    if not log:
        raise HTTPException(404, "Custom workout not found")
    return log


def _get_index(request: Request):
    index = getattr(request.app.state, "exercise_index", None)
    if index is None:
        raise HTTPException(503, "Exercise index not loaded yet")
    return index


def _out(log: WorkoutLog) -> WorkoutLogOut:
    data = WorkoutLogOut.model_validate(log)
    if log.workout_type:
        data.workout_label = _focus(log.workout_type).get("label") or log.workout_type.replace("_", " ").title()
    return data


def _sorted_exercises(log: WorkoutLog) -> list[WorkoutExercise]:
    return sorted(log.exercises, key=lambda e: e.position)


def _repack_positions(log: WorkoutLog) -> None:
    for i, we in enumerate(_sorted_exercises(log)):
        we.position = i


def _clone_exercises(src: WorkoutLog, dst: WorkoutLog) -> None:
    for we in _sorted_exercises(src):
        dst.exercises.append(WorkoutExercise(
            exercise_id=we.exercise_id,
            exercise_name=we.exercise_name,
            position=we.position,
            sets=we.sets,
            reps=we.reps,
            duration_seconds=we.duration_seconds,
            rest_seconds=we.rest_seconds,
            weight_kg=we.weight_kg,
            notes=we.notes,
        ))


def _injury_warning(db: Session, index, user_id: int, exercise: dict) -> str | None:
    """Warning string if this exercise is currently suppressed/cooldown for the
    user, with up to 3 substitute names. None if it's fine."""
    sg = SuggestibilityEngine(db).compute(user_id, exercise)
    if sg.state not in _BLOCKED:
        return None
    subs = SubstitutionEngine(db=db, index=index).find_substitutes(user_id, exercise["id"], top_k=3)
    reason = sg.suppression_reason or sg.state.value
    tail = f" Safer options: {', '.join(s.exercise['name'] for s in subs)}." if subs else ""
    return f"{exercise['name']} is currently flagged ({reason}). It's still in your workout.{tail}"


# ── Static option lists ──────────────────────────────────────────────────────

@router.get("/options")
def builder_options():
    return {
        "workout_types": CUSTOM_WORKOUT_TYPES,
        "focus_options": [{"value": k, "label": v["label"]} for k, v in BUILDER_FOCUS.items()],
        "feedback": ["liked", "disliked", "rejected"],
        "rejection_reasons": sorted(REJECTION_REASONS),
    }


# ── Workout CRUD ─────────────────────────────────────────────────────────────

@router.post("", response_model=WorkoutLogOut, status_code=201)
def create_workout(user_id: int, body: WorkoutCreate, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = WorkoutLog(
        user_id=user_id,
        name=body.name,
        workout_type=body.workout_type,
        source=_SOURCE,
        is_template=body.is_template,
        notes=body.notes,
        started_at=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return _out(log)


@router.get("", response_model=list[WorkoutLogOut])
def list_workouts(
    user_id: int,
    db: Session = Depends(get_db),
    templates: str = Query("include", pattern="^(include|only|exclude)$"),
    include_completed: bool = Query(True),
):
    _get_user_or_404(user_id, db)
    q = db.query(WorkoutLog).filter(WorkoutLog.user_id == user_id, WorkoutLog.source == _SOURCE)
    if templates == "only":
        q = q.filter(WorkoutLog.is_template.is_(True))
    elif templates == "exclude":
        q = q.filter(WorkoutLog.is_template.is_(False))
    if not include_completed:
        q = q.filter(WorkoutLog.completed_at.is_(None))
    return [_out(w) for w in q.order_by(WorkoutLog.started_at.desc()).all()]


@router.get("/{workout_id}", response_model=WorkoutLogOut)
def get_workout(user_id: int, workout_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    return _out(_get_workout_or_404(user_id, workout_id, db))


@router.patch("/{workout_id}", response_model=WorkoutLogOut)
def update_workout(user_id: int, workout_id: int, body: WorkoutUpdate, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(log, field, value)
    db.commit()
    db.refresh(log)
    return _out(log)


@router.delete("/{workout_id}", status_code=204)
def delete_workout(user_id: int, workout_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    db.delete(log)
    db.commit()
    return Response(status_code=204)


@router.post("/{workout_id}/duplicate", response_model=WorkoutLogOut, status_code=201)
def duplicate_workout(
    user_id: int,
    workout_id: int,
    db: Session = Depends(get_db),
    name: str | None = Query(None),
    as_template: bool | None = Query(None),
):
    _get_user_or_404(user_id, db)
    src = _get_workout_or_404(user_id, workout_id, db)
    copy = WorkoutLog(
        user_id=user_id,
        name=name or f"{src.name or 'Workout'} (copy)",
        workout_type=src.workout_type,
        source=_SOURCE,
        is_template=src.is_template if as_template is None else as_template,
        notes=src.notes,
        started_at=datetime.now(timezone.utc),
    )
    _clone_exercises(src, copy)
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _out(copy)


@router.post("/from-log/{log_id}", response_model=WorkoutLogOut, status_code=201)
def build_from_existing_log(
    user_id: int,
    log_id: int,
    db: Session = Depends(get_db),
    name: str | None = Query(None),
    as_template: bool = Query(True),
):
    """Seed a custom workout from any of the user's existing logs — e.g. tweak a
    generated daily program by hand."""
    _get_user_or_404(user_id, db)
    src = db.query(WorkoutLog).filter(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id).first()
    if not src:
        raise HTTPException(404, "Source workout log not found")
    label = _focus(src.workout_type).get("label", "Workout")
    copy = WorkoutLog(
        user_id=user_id,
        name=name or f"{src.name or label} (edited)",
        workout_type=src.workout_type,
        source=_SOURCE,
        is_template=as_template,
        started_at=datetime.now(timezone.utc),
    )
    _clone_exercises(src, copy)
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _out(copy)


# ── Exercise items ───────────────────────────────────────────────────────────

@router.post("/{workout_id}/exercises", response_model=WorkoutMutationResponse, status_code=201)
def add_exercise(
    user_id: int, workout_id: int, body: ExerciseAdd,
    request: Request, db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    index = _get_index(request)

    exercise = index.get_by_id(body.exercise_id)
    if exercise is None:
        raise HTTPException(404, f"Exercise '{body.exercise_id}' not found")

    warnings: list[str] = []
    if any(we.exercise_id == body.exercise_id for we in log.exercises):
        warnings.append(f"{exercise['name']} is already in this workout — added again.")

    items = _sorted_exercises(log)
    insert_at = len(items) if body.position is None else min(body.position, len(items))
    for we in items[insert_at:]:
        we.position += 1

    log.exercises.append(WorkoutExercise(
        exercise_id=body.exercise_id,
        exercise_name=exercise["name"],
        position=insert_at,
        sets=body.sets,
        reps=body.reps,
        duration_seconds=body.duration_seconds,
        rest_seconds=body.rest_seconds,
        weight_kg=body.weight_kg,
        notes=body.notes,
    ))

    injury = _injury_warning(db, index, user_id, exercise)
    if injury:
        warnings.append(injury)

    db.commit()
    db.refresh(log)
    return WorkoutMutationResponse(workout=_out(log), warnings=warnings)


@router.patch("/{workout_id}/exercises/{we_id}", response_model=WorkoutLogOut)
def update_exercise(
    user_id: int, workout_id: int, we_id: int, body: ExerciseUpdate,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    we = next((e for e in log.exercises if e.id == we_id), None)
    if we is None:
        raise HTTPException(404, "Exercise not in this workout")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(we, field, value)
    if (we.reps in (None, "")) and we.duration_seconds is None:
        raise HTTPException(400, "An exercise needs reps or duration_seconds.")

    db.commit()
    db.refresh(log)
    return _out(log)


@router.delete("/{workout_id}/exercises/{we_id}", response_model=WorkoutLogOut)
def remove_exercise(user_id: int, workout_id: int, we_id: int, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    we = next((e for e in log.exercises if e.id == we_id), None)
    if we is None:
        raise HTTPException(404, "Exercise not in this workout")
    db.delete(we)
    db.commit()
    db.refresh(log)
    _repack_positions(log)
    db.commit()
    db.refresh(log)
    return _out(log)


@router.put("/{workout_id}/exercises/order", response_model=WorkoutLogOut)
def reorder_exercises(
    user_id: int, workout_id: int, body: ReorderRequest, db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    current = {e.id for e in log.exercises}
    if set(body.exercise_ids) != current or len(body.exercise_ids) != len(current):
        raise HTTPException(400, "exercise_ids must be a permutation of this workout's exercise ids")
    order = {eid: i for i, eid in enumerate(body.exercise_ids)}
    for we in log.exercises:
        we.position = order[we.id]
    db.commit()
    db.refresh(log)
    return _out(log)


# ── Suggested exercise picker ────────────────────────────────────────────────

@router.get("/{workout_id}/suggestions", response_model=SuggestionResponse)
def suggest_exercises(
    user_id: int, workout_id: int, request: Request, db: Session = Depends(get_db),
    q: str | None = Query(None),
    body_part: list[str] = Query(default=[]),
    muscle: list[str] = Query(default=[]),
    movement_pattern: list[str] = Query(default=[]),
    equipment: list[str] = Query(default=[]),
    equipment_match: str = Query("uses_any", pattern="^(uses_any|doable_with)$"),
    force_direction: list[str] = Query(default=[]),
    mechanic: str | None = Query(None, pattern="^(compound|isolation)$"),
    sort: str = Query("relevance", pattern="^(relevance|name|compound_first)$"),
    eligibility: str = Query("flag_suppressed", pattern="^(all|eligible_only|flag_suppressed)$"),
    exclude_added: bool = Query(True),
    facets: bool = Query(False),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    index = _get_index(request)

    pool = index.all_exercises()
    # Default the pattern scope to the workout's type unless the caller filters
    # patterns explicitly or is running a free-text search.
    patterns = list(movement_pattern)
    if not patterns and not q:
        patterns = _focus(log.workout_type).get("patterns", [])
    patterns = [p for p in patterns if p in MOVEMENT_PATTERNS]

    added_ids = {we.exercise_id for we in log.exercises}
    query = ExerciseQuery(
        q=q, body_parts=body_part, muscles=muscle, equipment=equipment,
        equipment_match=equipment_match, movement_patterns=patterns,
        force_directions=force_direction, mechanic=mechanic,
        exclude_ids=added_ids if exclude_added else set(), sort=sort,
    )
    filtered = apply_filters(pool, query)

    sg_map = {
        r.exercise_id: r
        for r in SuggestibilityEngine(db).batch_compute(user_id, filtered)
    }
    if eligibility == "eligible_only":
        filtered = [e for e in filtered if sg_map[e["id"]].state not in _BLOCKED]

    page = filtered[offset : offset + limit]
    items = [
        SuggestionItem(
            exercise=ex,
            mechanic=mechanic_of(ex),
            already_added=ex["id"] in added_ids,
            suggestibility_state=sg_map[ex["id"]].state.value,
            suggestibility_reason=sg_map[ex["id"]].suppression_reason,
        )
        for ex in page
    ]

    resp = SuggestionResponse(
        workout_id=log.id, workout_type=log.workout_type,
        total=len(filtered), offset=offset, suggestions=items,
    )
    if facets:
        text_only = apply_filters(pool, ExerciseQuery(q=q))
        resp.facets = compute_facets(text_only)
    return resp


# ── Analysis ─────────────────────────────────────────────────────────────────

_WORK_SECONDS_PER_REP = 3
_DEFAULT_WORK_SECONDS = 35


def _exercise_seconds(we: WorkoutExercise) -> int:
    if we.duration_seconds:
        work = we.duration_seconds
    elif we.reps:
        m = re.search(r"\d+", we.reps)
        work = int(m.group()) * _WORK_SECONDS_PER_REP if m else _DEFAULT_WORK_SECONDS
    else:
        work = _DEFAULT_WORK_SECONDS
    return we.sets * (work + we.rest_seconds)


@router.get("/{workout_id}/analysis", response_model=WorkoutAnalysis)
def analyze_workout(user_id: int, workout_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    index = _get_index(request)

    exercises = _sorted_exercises(log)
    resolved = [(we, index.get_by_id(we.exercise_id)) for we in exercises]

    # Muscle coverage — activation summed across the workout, weighted by set
    # count, then normalised to the hardest-hit muscle.
    totals = {m: 0.0 for m in MUSCLES}
    for we, ex in resolved:
        if not ex:
            continue
        for m, v in ex["muscle_activation"].items():
            if m in totals:
                totals[m] += v * we.sets
    peak = max(totals.values(), default=0.0) or 1.0
    coverage = sorted(
        (
            MuscleCoverage(
                muscle=m,
                display_name=MUSCLE_DISPLAY.get(m, {}).get("display_name", m),
                activation=round(totals[m] / peak, 3),
            )
            for m in MUSCLES if totals[m] > 0
        ),
        key=lambda c: -c.activation,
    )

    pattern_breakdown = Counter(ex["movement_pattern"] for _, ex in resolved if ex)
    expected = _focus(log.workout_type).get("patterns", [])
    missing = [p for p in expected if pattern_breakdown.get(p, 0) == 0]

    sg_results = SuggestibilityEngine(db).batch_compute(user_id, [ex for _, ex in resolved if ex])
    conflicts = [
        f"{r.exercise_id.replace('_', ' ').title()}: {r.suppression_reason or r.state.value}"
        for r in sg_results if r.state in _BLOCKED
    ]

    est_minutes = round(sum(_exercise_seconds(we) for we in exercises) / 60)
    target = user.minutes_per_session
    if not target:
        verdict = "unknown"
    elif est_minutes < target * 0.6:
        verdict = "short"
    elif est_minutes > target * 1.3:
        verdict = "long"
    else:
        verdict = "on_target"

    warnings: list[str] = []
    if not exercises:
        warnings.append("This workout has no exercises yet.")
    if missing:
        warnings.append(
            f"No {', '.join(missing)} work for a {_focus(log.workout_type).get('label', 'this')} session."
        )
    if verdict == "long":
        warnings.append(f"Estimated {est_minutes} min vs your {target} min target — consider trimming a movement.")
    if verdict == "short":
        warnings.append(f"Estimated {est_minutes} min vs your {target} min target — room for another movement.")
    for c in conflicts:
        warnings.append(f"Injury/cooldown conflict — {c}")

    return WorkoutAnalysis(
        exercise_count=len(exercises),
        estimated_minutes=est_minutes,
        target_minutes=target,
        duration_verdict=verdict,
        muscle_coverage=coverage,
        pattern_breakdown=dict(pattern_breakdown),
        missing_patterns=missing,
        injury_conflicts=conflicts,
        warnings=warnings,
    )


# ── Start / complete a session ───────────────────────────────────────────────

@router.post("/{workout_id}/start", response_model=WorkoutLogOut, status_code=201)
def start_session(
    user_id: int, workout_id: int,
    on: date | None = Query(None, description="Schedule the session on this date (default: today)"),
    db: Session = Depends(get_db),
):
    """Clone this workout (usually a template) into a fresh session log. With no
    `on` date it's stamped now and ready to run; with a date it's scheduled onto
    that day of the week view (source="daily" so the weekly program picks it up),
    replacing any incomplete daily workout already sitting on that date."""
    _get_user_or_404(user_id, db)
    src = _get_workout_or_404(user_id, workout_id, db)

    if on is not None:
        started = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc).replace(hour=18)
        day_start = datetime.combine(on, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        clash = (
            db.query(WorkoutLog)
            .filter(
                WorkoutLog.user_id == user_id,
                WorkoutLog.source == "daily",
                WorkoutLog.started_at >= day_start,
                WorkoutLog.started_at < day_end,
                WorkoutLog.completed_at.is_(None),
            )
            .first()
        )
        if clash is not None:
            db.delete(clash)
            db.flush()

    session = WorkoutLog(
        user_id=user_id,
        name=src.name,
        workout_type=src.workout_type,
        source="daily" if on is not None else _SOURCE,
        is_template=False,
        notes=src.notes,
        started_at=started if on is not None else datetime.now(timezone.utc),
    )
    _clone_exercises(src, session)
    db.add(session)
    db.commit()
    db.refresh(session)
    return _out(session)


@router.post("/{workout_id}/complete", response_model=WorkoutLogOut)
def complete_session(
    user_id: int, workout_id: int, body: CompleteWorkoutRequest,
    db: Session = Depends(get_db),
):
    _get_user_or_404(user_id, db)
    log = _get_workout_or_404(user_id, workout_id, db)
    if log.is_template:
        raise HTTPException(400, "Can't complete a template — call /start first.")

    log.completed_at = datetime.now(timezone.utc)
    by_id = {we.id: we for we in log.exercises}

    for perf in body.performances:
        we = by_id.get(perf.workout_exercise_id)
        if we is None:
            raise HTTPException(404, f"workout_exercise_id {perf.workout_exercise_id} not in this workout")
        we.feedback = perf.feedback
        if perf.feedback == "rejected":
            reason = perf.rejection_reason if perf.rejection_reason in REJECTION_REASONS else "dont_like"
            db.add(RejectionEvent(
                user_id=user_id,
                exercise_id=we.exercise_id,
                exercise_name=we.exercise_name,
                reason=reason,
                note="Auto-logged from custom workout completion",
                created_at=datetime.now(timezone.utc),
            ))
        elif perf.feedback == "disliked":
            _record_soft_dislike(db, user_id, we.exercise_id, we.exercise_name)

    db.commit()
    db.refresh(log)
    return _out(log)
