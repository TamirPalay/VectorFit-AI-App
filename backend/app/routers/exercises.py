"""
Exercises router: read-only endpoints to browse the exercise dataset.

The ExerciseIndex is loaded once at startup and stored in app.state.
These endpoints are used by the custom builder's search and the dashboard.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from app.data.muscles import BODY_PART_NAMES, FORCE_DIRECTIONS, MOVEMENT_PATTERNS, MUSCLES
from app.services.exercise_filters import ExerciseQuery, apply_filters, compute_facets

router = APIRouter(prefix="/exercises", tags=["exercises"])


def _get_index(request: Request):
    index = getattr(request.app.state, "exercise_index", None)
    if index is None:
        raise HTTPException(status_code=503, detail="Exercise index not loaded yet")
    return index


@router.get("/filters")
def list_filter_options():
    """The vocabularies the quick-filter chips can use."""
    return {
        "body_part": BODY_PART_NAMES,
        "muscle": MUSCLES,
        "movement_pattern": sorted(MOVEMENT_PATTERNS),
        "force_direction": sorted(FORCE_DIRECTIONS),
        "mechanic": ["compound", "isolation"],
        "equipment_match": ["uses_any", "doable_with"],
        "sort": ["relevance", "name", "compound_first"],
    }


@router.get("")
def list_exercises(
    request: Request,
    q: str | None = Query(None, description="Free-text match on name + description"),
    body_part: list[str] = Query(default=[], description="e.g. chest, back, legs (OR-combined)"),
    muscle: list[str] = Query(default=[], description="Exact muscle id, activation >= 0.3 (OR-combined)"),
    movement_pattern: list[str] = Query(default=[], description="push/pull/hinge/squat/carry/core (OR-combined)"),
    equipment: list[str] = Query(default=[], description="Equipment items"),
    equipment_match: str = Query("uses_any", pattern="^(uses_any|doable_with)$"),
    force_direction: list[str] = Query(default=[], description="against_gravity/supported/horizontal/vertical"),
    mechanic: str | None = Query(None, pattern="^(compound|isolation)$"),
    exclude_ids: list[str] = Query(default=[], description="Exercise ids to omit (e.g. already added)"),
    sort: str = Query("relevance", pattern="^(relevance|name|compound_first)$"),
    facets: bool = Query(False, description="Also return chip counts for the current text query"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Search / browse the exercise dataset. All filters are AND-combined; values
    within a single multi-value filter are OR-combined. Deterministic, no LLM.
    """
    index = _get_index(request)
    all_exercises = index.all_exercises()

    query = ExerciseQuery(
        q=q,
        body_parts=body_part,
        muscles=muscle,
        equipment=equipment,
        equipment_match=equipment_match,
        movement_patterns=movement_pattern,
        force_directions=force_direction,
        mechanic=mechanic,
        exclude_ids=set(exclude_ids),
        sort=sort,
    )
    filtered = apply_filters(all_exercises, query)

    body = {
        "total": len(filtered),
        "offset": offset,
        "exercises": filtered[offset : offset + limit],
    }
    if facets:
        # Facet counts are computed over the text-query set only, so toggling a
        # chip doesn't make the other chip counts jump around.
        text_only = apply_filters(all_exercises, ExerciseQuery(q=q))
        body["facets"] = compute_facets(text_only)
    return body


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
