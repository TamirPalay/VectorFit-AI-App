"""
Exercises router: read-only endpoints to browse the exercise dataset.

The ExerciseIndex is loaded once at startup and stored in app.state.
These endpoints are used by the custom builder's search and the dashboard.
"""

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/exercises", tags=["exercises"])


def _get_index(request: Request):
    index = getattr(request.app.state, "exercise_index", None)
    if index is None:
        raise HTTPException(status_code=503, detail="Exercise index not loaded yet")
    return index


@router.get("")
def list_exercises(
    request: Request,
    movement_pattern: str | None = Query(None),
    equipment: str | None = Query(None, description="Filter by a single equipment item"),
    muscle: str | None = Query(None, description="Filter by a muscle with activation > 0.3"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List exercises with optional filters.
    All filters are AND-combined.
    """
    index = _get_index(request)
    exercises = index.all_exercises()

    if movement_pattern:
        exercises = [e for e in exercises if e["movement_pattern"] == movement_pattern]
    if equipment:
        exercises = [e for e in exercises if equipment in e["equipment_required"]]
    if muscle:
        exercises = [
            e for e in exercises
            if e["muscle_activation"].get(muscle, 0.0) >= 0.3
        ]

    total = len(exercises)
    page = exercises[offset : offset + limit]

    return {"total": total, "offset": offset, "exercises": page}


@router.get("/{exercise_id}")
def get_exercise(exercise_id: str, request: Request):
    index = _get_index(request)
    ex = index.get_by_id(exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail=f"Exercise '{exercise_id}' not found")
    return ex


@router.get("/{exercise_id}/similar")
def similar_exercises(
    exercise_id: str,
    request: Request,
    top_k: int = Query(5, ge=1, le=20),
    blocked_flags: str = Query(
        "",
        description="Comma-separated joint_stress_flags to exclude (e.g. high_shoulder_flexion_under_load)",
    ),
):
    """
    Find the most muscle-activation-similar exercises to the given one,
    filtered by blocked joint-stress flags.
    """
    index = _get_index(request)
    if not index.get_by_id(exercise_id):
        raise HTTPException(status_code=404, detail=f"Exercise '{exercise_id}' not found")

    flags_set = {f.strip() for f in blocked_flags.split(",") if f.strip()}
    results = index.find_similar(exercise_id, top_k=top_k, blocked_flags=flags_set)
    return {"source_id": exercise_id, "results": results}
