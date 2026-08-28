"""
Personal dashboard — Stage 9.

Read-only analytics over a user's completed workout history + daily health
metrics. Every charting endpoint also accepts ?format=png to return a rendered
matplotlib/seaborn image, so the dashboard is demoable before the React
frontend (Stage 10) exists. No LLM anywhere in this stage.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services import dashboard_analytics as da

router = APIRouter(prefix="/users/{user_id}/dashboard", tags=["dashboard"])

_PNG = "image/png"


def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _index(request: Request):
    idx = getattr(request.app.state, "exercise_index", None)
    if idx is None:
        raise HTTPException(503, "Exercise index not loaded yet")
    return idx


def _range(request: Request, db: Session, user_id: int, date_from: date | None, date_to: date | None,
           status: str = "completed", days: int = 90):
    user = _get_user_or_404(user_id, db)
    index = _index(request)
    start, end = da.default_range(date_from, date_to, days)
    sessions_df, exercises_df = da.load_frames(db, index, user_id, start, end, status)
    return user, index, start, end, sessions_df, exercises_df


# ── Summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def summary(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
):
    user, index, start, end, s_df, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    m_df = da.load_metrics(db, user_id, start, end)
    return da.build_summary(db, index, user, s_df, e_df, m_df, start, end)


# ── Muscle activation over time (data for a frontend line chart) ─────────────

@router.get("/muscle-activation")
def muscle_activation(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    bucket: str = Query("week", pattern="^(day|week|month)$"),
    group: str = Query("body_part", pattern="^(muscle|body_part)$"),
    normalize: str = Query("none", pattern="^(none|per_bucket)$"),
):
    """Time-bucketed activation-load matrix (buckets x muscles). For the visual
    body map, use /muscle-map."""
    *_, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    return da.muscle_activation(e_df, bucket, group, normalize)


# ── Anatomical muscle map (front / back body, shaded by activation) ──────────

@router.get("/muscle-map")
def muscle_map(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    view: str = Query("both", pattern="^(both|front|back)$"),
    theme: str = Query("auto", pattern="^(auto|light|dark)$"),
    format: str = Query("svg", pattern="^(svg|json)$"),
):
    """Anatomical front/back body diagram — each muscle region's <path> is filled
    with a colour scaled to that muscle's activation-load over the range,
    relative to the hardest-hit muscle. Returns SVG (renders in a browser,
    theme-aware). format=json returns the raw per-muscle totals instead."""
    user, index, start, end, s_df, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    totals = da.muscle_totals(e_df)
    n_workouts = 0 if s_df.empty else int(s_df["log_id"].nunique())
    if format == "json":
        return {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "workouts": n_workouts,
            "totals": totals,
            "peak_muscle": max(totals, key=totals.get) if any(totals.values()) else None,
        }
    title = f"Muscle map · {start.isoformat()} to {end.isoformat()}"
    subtitle = (f"{n_workouts} completed workout{'s' if n_workouts != 1 else ''}"
                if n_workouts else "No completed workouts in this range")
    svg = da.render_muscle_map_svg(totals, title, subtitle, view, theme)
    return Response(svg, media_type="image/svg+xml")


# ── Volume ───────────────────────────────────────────────────────────────────

@router.get("/volume")
def volume(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    bucket: str = Query("week", pattern="^(day|week|month)$"),
    format: str = Query("json", pattern="^(json|png)$"),
):
    _, _, _, _, s_df, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    data = da.volume_series(s_df, e_df, bucket)
    if format == "png":
        return Response(da.png_bar(data["buckets"], data["activation_load"],
                                   f"Activation-load by {bucket}", "activation-load"), media_type=_PNG)
    return data


# ── Workouts completed over time ────────────────────────────────────────────

@router.get("/workouts")
def workouts(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    bucket: str = Query("week", pattern="^(day|week|month)$"),
    format: str = Query("json", pattern="^(json|png)$"),
):
    user, _, start, end, s_df, _ = _range(request, db, user_id, date_from, date_to, days=90)
    data = da.workout_counts(s_df, user, start, end, bucket)
    if format == "png":
        return Response(da.png_bar(data["buckets"], data["counts"],
                                   f"Workouts completed by {bucket}", "workouts"), media_type=_PNG)
    return data


# ── Consistency calendar ────────────────────────────────────────────────────

@router.get("/consistency")
def consistency(
    user_id: int, request: Request, db: Session = Depends(get_db),
    weeks: int = Query(12, ge=1, le=53),
):
    user, index, start, end, s_df, _ = _range(request, db, user_id, None, None, days=weeks * 7)
    return da.consistency(s_df, weeks, end)


# ── Balance / neglect ───────────────────────────────────────────────────────

@router.get("/balance")
def balance(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    format: str = Query("json", pattern="^(json|png)$"),
):
    *_, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    data = da.balance(e_df)
    if format == "png":
        return Response(da.png_bar(list(data["by_group"].keys()), list(data["by_group"].values()),
                                   "Activation-load by body part", "activation-load"), media_type=_PNG)
    return data


# ── Movement patterns ───────────────────────────────────────────────────────

@router.get("/patterns")
def patterns(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
):
    *_, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    return da.patterns(e_df)


# ── Rejections ──────────────────────────────────────────────────────────────

@router.get("/rejections")
def rejections(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    bucket: str = Query("week", pattern="^(day|week|month)$"),
):
    _get_user_or_404(user_id, db)
    start, end = da.default_range(date_from, date_to, 90)
    return da.rejections(db, user_id, start, end, bucket)


# ── Substitutions (the safety engine at work) ───────────────────────────────

@router.get("/substitutions")
def substitutions(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
):
    _, _, _, _, s_df, e_df = _range(request, db, user_id, date_from, date_to, days=90)
    return da.substitutions(s_df, e_df)


# ── Daily health metrics ────────────────────────────────────────────────────

@router.get("/metrics")
def metrics(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    metric: str = Query("steps"),
    format: str = Query("json", pattern="^(json|png)$"),
):
    _get_user_or_404(user_id, db)
    start, end = da.default_range(date_from, date_to, 60)
    m_df = da.load_metrics(db, user_id, start, end)
    try:
        data = da.metrics_series(m_df, metric)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if format == "png":
        return Response(da.png_line(data["dates"], data["values"], data["rolling_7d"],
                                    metric.replace("_", " ").title(), metric), media_type=_PNG)
    return data


# ── Injury timeline ─────────────────────────────────────────────────────────

@router.get("/injuries")
def injuries(user_id: int, request: Request, db: Session = Depends(get_db)):
    _get_user_or_404(user_id, db)
    return da.injuries_timeline(db, _index(request), user_id)


# ── Personal records (opt-in) ──────────────────────────────────────────────

@router.get("/personal-records")
def personal_records(
    user_id: int, request: Request, db: Session = Depends(get_db),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
):
    user, _, _, _, _, e_df = _range(request, db, user_id, date_from, date_to, days=365)
    data = da.personal_records(e_df)
    data["enabled"] = user.show_personal_records
    return data
