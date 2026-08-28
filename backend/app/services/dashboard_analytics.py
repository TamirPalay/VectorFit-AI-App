"""
Dashboard analytics — Stage 9.

Loads a user's completed workout history + daily health metrics into pandas
frames, then produces the aggregations the dashboard endpoints return (JSON) and,
optionally, rendered matplotlib/seaborn charts (PNG). No LLM.

The unit everything rolls up from is **activation-load**: for each exercise in a
workout, sum(muscle_activation[m] * sets) per muscle. It's a per-muscle stimulus
proxy that buckets cleanly by day / week / month.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")  # headless — must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.data.muscles import MUSCLE_DISPLAY, MUSCLES  # noqa: E402
from app.models.rejection import RejectionEvent  # noqa: E402
from app.models.user import Injury, User  # noqa: E402
from app.models.workout_log import WorkoutExercise, WorkoutLog  # noqa: E402

# ── Muscle → coarse group (1:1, for the grouped views) ───────────────────────
MUSCLE_GROUP: dict[str, str] = {
    "chest": "chest", "serratus_anterior": "chest",
    "anterior_deltoid": "shoulders", "lateral_deltoid": "shoulders", "posterior_deltoid": "shoulders",
    "biceps": "arms", "triceps": "arms", "forearms": "arms",
    "lats": "back", "rhomboids": "back", "traps_upper": "back", "traps_mid": "back",
    "erector_spinae": "lower_back",
    "abs": "core", "obliques": "core", "hip_flexors": "core",
    "quads": "quads", "hamstrings": "hamstrings", "glutes": "glutes",
    "adductors": "legs_other", "abductors": "legs_other", "calves": "calves",
}
_UPPER_GROUPS = {"chest", "shoulders", "arms", "back"}
_LOWER_GROUPS = {"quads", "hamstrings", "glutes", "calves", "legs_other"}

_BUCKET_FREQ = {"day": "D", "week": "W-MON", "month": "MS"}
_WORK_SECONDS_PER_REP = 3
_DEFAULT_WORK_SECONDS = 35


# ── Loading ──────────────────────────────────────────────────────────────────

def default_range(start: date | None, end: date | None, days: int = 90) -> tuple[date, date]:
    end = end or datetime.now(timezone.utc).date()
    start = start or (end - timedelta(days=days))
    return start, end


def _as_date(dt: datetime | None) -> date | None:
    return dt.date() if dt else None


def _est_minutes(sets: int, reps: str | None, duration_seconds: int | None, rest: int) -> float:
    if duration_seconds:
        work = duration_seconds
    elif reps:
        m = re.search(r"\d+", reps)
        work = int(m.group()) * _WORK_SECONDS_PER_REP if m else _DEFAULT_WORK_SECONDS
    else:
        work = _DEFAULT_WORK_SECONDS
    return sets * (work + (rest or 0)) / 60


def load_frames(
    db: Session,
    index,
    user_id: int,
    start: date,
    end: date,
    status: str = "completed",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (sessions_df, exercises_df) for the user's workouts whose
    started_at date falls in [start, end].

    sessions_df:  one row per WorkoutLog  — log_id, date, source, workout_type,
                  name, is_template, completed, exercise_count, total_sets,
                  est_minutes, swap_count
    exercises_df: one row per WorkoutExercise — log_id, date, exercise_id, name,
                  movement_pattern, sets, reps, duration_seconds, weight_kg,
                  substituted_for_id, plus one column per muscle holding
                  activation-load (activation * sets)
    """
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    q = (
        db.query(WorkoutLog)
        .filter(
            WorkoutLog.user_id == user_id,
            WorkoutLog.started_at >= start_dt,
            WorkoutLog.started_at < end_dt,
            WorkoutLog.is_template.is_(False),
        )
    )
    if status == "completed":
        q = q.filter(WorkoutLog.completed_at.isnot(None))
    elif status == "planned":
        q = q.filter(WorkoutLog.completed_at.is_(None))
    logs = q.all()

    session_rows: list[dict] = []
    exercise_rows: list[dict] = []
    for log in logs:
        d = _as_date(log.started_at)
        swap_count = sum(1 for we in log.exercises if we.substituted_for_id)
        total_sets = sum(we.sets for we in log.exercises)
        est = sum(_est_minutes(we.sets, we.reps, we.duration_seconds, we.rest_seconds) for we in log.exercises)
        session_rows.append({
            "log_id": log.id, "date": d, "source": log.source,
            "workout_type": log.workout_type, "name": log.name,
            "completed": log.completed_at is not None,
            "exercise_count": len(log.exercises), "total_sets": total_sets,
            "est_minutes": round(est, 1), "swap_count": swap_count,
        })
        for we in log.exercises:
            ex = index.get_by_id(we.exercise_id)
            row = {
                "log_id": log.id, "date": d, "source": log.source,
                "workout_type": log.workout_type,
                "exercise_id": we.exercise_id, "exercise_name": we.exercise_name,
                "movement_pattern": ex["movement_pattern"] if ex else None,
                "sets": we.sets, "reps": we.reps, "duration_seconds": we.duration_seconds,
                "weight_kg": we.weight_kg, "substituted_for_id": we.substituted_for_id,
            }
            activation = ex["muscle_activation"] if ex else {}
            for m in MUSCLES:
                row[m] = activation.get(m, 0.0) * we.sets
            exercise_rows.append(row)

    sessions_df = pd.DataFrame(session_rows)
    exercises_df = pd.DataFrame(exercise_rows)
    for df in (sessions_df, exercises_df):
        if not df.empty:
            df["ts"] = pd.to_datetime(df["date"])
    return sessions_df, exercises_df


def load_metrics(db: Session, user_id: int, start: date, end: date) -> pd.DataFrame:
    from app.models.daily_metric import DailyMetric

    rows = (
        db.query(DailyMetric)
        .filter(DailyMetric.user_id == user_id, DailyMetric.date >= start, DailyMetric.date <= end)
        .order_by(DailyMetric.date)
        .all()
    )
    df = pd.DataFrame([{
        "date": r.date, "steps": r.steps, "active_calories": r.active_calories,
        "resting_heart_rate": r.resting_heart_rate, "body_weight_kg": r.body_weight_kg,
        "sleep_hours": r.sleep_hours, "energy_level": r.energy_level,
    } for r in rows])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["date"])
    return df


# ── Aggregations ─────────────────────────────────────────────────────────────

def _bucket_key(freq: str):
    return pd.Grouper(key="ts", freq=freq)


def muscle_activation(
    exercises_df: pd.DataFrame, bucket: str = "week", group: str = "muscle", normalize: str = "none",
) -> dict:
    freq = _BUCKET_FREQ[bucket]
    cols = MUSCLES
    if exercises_df.empty:
        return {"bucket": bucket, "group": group, "buckets": [], "series": {}, "columns": []}

    grouped = exercises_df.groupby(_bucket_key(freq))[cols].sum()

    if group == "body_part":
        collapsed = defaultdict(lambda: pd.Series(0.0, index=grouped.index))
        for m in cols:
            collapsed[MUSCLE_GROUP[m]] = collapsed[MUSCLE_GROUP[m]] + grouped[m]
        matrix = pd.DataFrame(collapsed)
    else:
        matrix = grouped

    matrix = matrix.round(2)
    if normalize == "per_bucket":
        totals = matrix.sum(axis=1).replace(0, 1)
        matrix = (matrix.div(totals, axis=0) * 100).round(1)

    buckets = [ts.date().isoformat() for ts in matrix.index]
    series = {col: [float(v) for v in matrix[col].tolist()] for col in matrix.columns}
    labels = {
        m: (MUSCLE_DISPLAY.get(m, {}).get("display_name", m) if group == "muscle" else m.replace("_", " ").title())
        for m in matrix.columns
    }
    return {
        "bucket": bucket, "group": group, "normalize": normalize,
        "columns": list(matrix.columns), "labels": labels,
        "buckets": buckets, "series": series,
    }


def volume_series(sessions_df: pd.DataFrame, exercises_df: pd.DataFrame, bucket: str = "week") -> dict:
    freq = _BUCKET_FREQ[bucket]
    if sessions_df.empty:
        return {"bucket": bucket, "buckets": [], "workouts": [], "sets": [], "activation_load": [], "by_pattern": {}}

    s = sessions_df.groupby(_bucket_key(freq)).agg(
        workouts=("log_id", "nunique"), sets=("total_sets", "sum"), minutes=("est_minutes", "sum")
    )
    load = exercises_df.assign(load=exercises_df[MUSCLES].sum(axis=1)).groupby(_bucket_key(freq))["load"].sum()
    pat = (
        exercises_df.dropna(subset=["movement_pattern"])
        .groupby([_bucket_key(freq), "movement_pattern"])["sets"].sum().unstack(fill_value=0)
    )
    idx = s.index
    buckets = [ts.date().isoformat() for ts in idx]
    return {
        "bucket": bucket,
        "buckets": buckets,
        "workouts": [int(x) for x in s["workouts"]],
        "sets": [int(x) for x in s["sets"]],
        "minutes": [round(float(x)) for x in s["minutes"]],
        "activation_load": [round(float(load.get(ts, 0.0)), 1) for ts in idx],
        "by_pattern": {p: [int(pat.loc[ts, p]) if (ts in pat.index and p in pat.columns) else 0 for ts in idx]
                       for p in pat.columns},
    }


def _streak_days(dates: set[date], today: date) -> int:
    streak, cur = 0, today
    # allow the streak to still count if they haven't trained *today* yet
    if cur not in dates:
        cur -= timedelta(days=1)
    while cur in dates:
        streak += 1
        cur -= timedelta(days=1)
    return streak


def workout_counts(sessions_df: pd.DataFrame, user: User, start: date, end: date, bucket: str = "week") -> dict:
    freq = _BUCKET_FREQ[bucket]
    total_weeks = max(1, ((end - start).days + 1) / 7)
    target = round(user.days_per_week * total_weeks)

    if sessions_df.empty:
        return {"bucket": bucket, "buckets": [], "counts": [], "by_source": {},
                "total": 0, "target": target, "adherence_pct": 0.0, "current_streak_days": 0}

    g = sessions_df.groupby([_bucket_key(freq), "source"])["log_id"].nunique().unstack(fill_value=0)
    idx = g.index
    buckets = [ts.date().isoformat() for ts in idx]
    total = int(sessions_df["log_id"].nunique())
    return {
        "bucket": bucket,
        "buckets": buckets,
        "counts": [int(g.loc[ts].sum()) for ts in idx],
        "by_source": {src: [int(g.loc[ts, src]) for ts in idx] for src in g.columns},
        "total": total,
        "target": target,
        "adherence_pct": round(100 * total / target, 1) if target else None,
        "current_streak_days": _streak_days(set(sessions_df["date"]), end),
    }


def consistency(sessions_df: pd.DataFrame, weeks: int, end: date) -> dict:
    start = end - timedelta(days=weeks * 7 - 1)
    counts: dict[str, int] = {}
    if not sessions_df.empty:
        per_day = sessions_df.groupby("date")["log_id"].nunique()
        for d, c in per_day.items():
            if start <= d <= end:
                counts[d.isoformat()] = int(c)
    return {"start": start.isoformat(), "end": end.isoformat(), "weeks": weeks, "counts": counts,
            "active_days": len(counts), "total_days": weeks * 7}


def balance(exercises_df: pd.DataFrame) -> dict:
    if exercises_df.empty:
        return {"by_group": {}, "shares": {}, "push_pull_ratio": None, "upper_lower_ratio": None, "undertrained": []}

    group_load: dict[str, float] = defaultdict(float)
    for m in MUSCLES:
        group_load[MUSCLE_GROUP[m]] += float(exercises_df[m].sum())
    total = sum(group_load.values()) or 1.0
    shares = {g: round(100 * v / total, 1) for g, v in group_load.items()}

    pat_sets = exercises_df.dropna(subset=["movement_pattern"]).groupby("movement_pattern")["sets"].sum()
    push, pull = float(pat_sets.get("push", 0)), float(pat_sets.get("pull", 0))
    upper = sum(v for g, v in group_load.items() if g in _UPPER_GROUPS)
    lower = sum(v for g, v in group_load.items() if g in _LOWER_GROUPS)

    peak = max(group_load.values()) if group_load else 0.0
    undertrained = sorted(
        [g for g, v in group_load.items() if peak and v < 0.35 * peak],
        key=lambda g: group_load[g],
    )
    return {
        "by_group": {g: round(v, 1) for g, v in sorted(group_load.items(), key=lambda kv: -kv[1])},
        "shares": dict(sorted(shares.items(), key=lambda kv: -kv[1])),
        "push_pull_ratio": round(push / pull, 2) if pull else None,
        "upper_lower_ratio": round(upper / lower, 2) if lower else None,
        "undertrained": undertrained,
    }


def patterns(exercises_df: pd.DataFrame) -> dict:
    if exercises_df.empty:
        return {"by_pattern_sets": {}, "by_pattern_exercises": {}, "shares": {}}
    d = exercises_df.dropna(subset=["movement_pattern"])
    sets = d.groupby("movement_pattern")["sets"].sum()
    exs = d.groupby("movement_pattern")["exercise_id"].count()
    total = float(sets.sum()) or 1.0
    return {
        "by_pattern_sets": {k: int(v) for k, v in sets.sort_values(ascending=False).items()},
        "by_pattern_exercises": {k: int(v) for k, v in exs.items()},
        "shares": {k: round(100 * v / total, 1) for k, v in sets.sort_values(ascending=False).items()},
    }


def rejections(db: Session, user_id: int, start: date, end: date, bucket: str = "week") -> dict:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    rows = (
        db.query(RejectionEvent)
        .filter(RejectionEvent.user_id == user_id,
                RejectionEvent.created_at >= start_dt, RejectionEvent.created_at < end_dt)
        .all()
    )
    if not rows:
        return {"total": 0, "by_reason": {}, "top_exercises": [], "bucket": bucket, "buckets": [], "counts": []}
    df = pd.DataFrame([{"reason": r.reason, "exercise_name": r.exercise_name,
                        "ts": pd.to_datetime(r.created_at)} for r in rows])
    by_reason = df["reason"].value_counts().to_dict()
    top = df["exercise_name"].value_counts().head(5)
    series = df.groupby(_bucket_key(_BUCKET_FREQ[bucket]))["reason"].count()
    return {
        "total": len(rows),
        "by_reason": {k: int(v) for k, v in by_reason.items()},
        "top_exercises": [{"exercise": k, "count": int(v)} for k, v in top.items()],
        "bucket": bucket,
        "buckets": [ts.date().isoformat() for ts in series.index],
        "counts": [int(v) for v in series.values],
    }


def substitutions(sessions_df: pd.DataFrame, exercises_df: pd.DataFrame) -> dict:
    if exercises_df.empty:
        return {"total_swaps": 0, "workouts_with_swaps": 0, "swap_rate_pct": None, "top_swapped_out": []}
    swaps = exercises_df.dropna(subset=["substituted_for_id"])
    total_ex = len(exercises_df)
    top = (
        swaps["substituted_for_id"].map(lambda s: s.replace("_", " ").title())
        .value_counts().head(5)
    )
    return {
        "total_swaps": int(len(swaps)),
        "workouts_with_swaps": int((sessions_df["swap_count"] > 0).sum()) if not sessions_df.empty else 0,
        "swap_rate_pct": round(100 * len(swaps) / total_ex, 1) if total_ex else None,
        "top_swapped_out": [{"exercise": k, "count": int(v)} for k, v in top.items()],
    }


_METRIC_COLS = {"steps", "active_calories", "resting_heart_rate", "body_weight_kg", "sleep_hours", "energy_level"}


def metrics_series(metrics_df: pd.DataFrame, metric: str) -> dict:
    if metric not in _METRIC_COLS:
        raise ValueError(f"Unknown metric '{metric}'. Valid: {sorted(_METRIC_COLS)}")
    if metrics_df.empty or metrics_df[metric].dropna().empty:
        return {"metric": metric, "dates": [], "values": [], "rolling_7d": [], "summary": {}}
    d = metrics_df[["date", metric]].dropna(subset=[metric]).sort_values("date")
    roll = d[metric].rolling(7, min_periods=1).mean().round(2)
    vals = d[metric].tolist()
    return {
        "metric": metric,
        "dates": [x.isoformat() for x in d["date"]],
        "values": [float(v) for v in vals],
        "rolling_7d": [float(v) for v in roll],
        "summary": {
            "avg": round(float(d[metric].mean()), 2),
            "min": float(d[metric].min()),
            "max": float(d[metric].max()),
            "latest": float(vals[-1]),
            "change": round(float(vals[-1] - vals[0]), 2),
        },
    }


def injuries_timeline(db: Session, index, user_id: int) -> dict:
    injuries = db.query(Injury).filter(Injury.user_id == user_id).order_by(Injury.created_at).all()
    today = datetime.now(timezone.utc).date()
    out = []
    for inj in injuries:
        start = _as_date(inj.created_at)
        end = _as_date(inj.healed_at)
        # workouts trained during the injury window vs an equal window before it
        window = (end or today) - start
        before_start = start - window
        during = _count_workouts(db, user_id, start, end or today)
        before = _count_workouts(db, user_id, before_start, start - timedelta(days=1))
        out.append({
            "body_part": inj.body_part, "severity": inj.severity,
            "start": start.isoformat(), "end": end.isoformat() if end else None,
            "ongoing": end is None,
            "duration_days": ((end or today) - start).days,
            "workouts_during": during, "workouts_before_equal_window": before,
        })
    return {"injuries": out}


def _count_workouts(db: Session, user_id: int, start: date, end: date) -> int:
    if end < start:
        return 0
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return (
        db.query(WorkoutLog)
        .filter(WorkoutLog.user_id == user_id, WorkoutLog.is_template.is_(False),
                WorkoutLog.completed_at.isnot(None),
                WorkoutLog.started_at >= start_dt, WorkoutLog.started_at < end_dt)
        .count()
    )


def personal_records(exercises_df: pd.DataFrame) -> dict:
    if exercises_df.empty:
        return {"records": []}
    weighted = exercises_df.dropna(subset=["weight_kg"])
    weighted = weighted[weighted["weight_kg"] > 0]
    if weighted.empty:
        return {"records": []}
    recs = []
    for ex_id, grp in weighted.groupby("exercise_id"):
        best = grp.loc[grp["weight_kg"].idxmax()]
        first = grp.loc[grp["date"].idxmin()]
        recs.append({
            "exercise_id": ex_id,
            "exercise_name": best["exercise_name"],
            "best_weight_kg": float(best["weight_kg"]),
            "achieved_on": best["date"].isoformat(),
            "first_weight_kg": float(first["weight_kg"]),
            "first_on": first["date"].isoformat(),
            "gain_kg": round(float(best["weight_kg"] - first["weight_kg"]), 1),
            "sessions": int(grp["log_id"].nunique()),
        })
    recs.sort(key=lambda r: -r["sessions"])
    return {"records": recs}


def build_summary(
    db: Session, index, user: User, sessions_df: pd.DataFrame, exercises_df: pd.DataFrame,
    metrics_df: pd.DataFrame, start: date, end: date,
) -> dict:
    today = end
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def _count_since(d: date) -> int:
        return 0 if sessions_df.empty else int(sessions_df[sessions_df["date"] >= d]["log_id"].nunique())

    bal = balance(exercises_df)
    wc = workout_counts(sessions_df, user, start, end, "week")

    def _metric_avg(col: str, days: int) -> float | None:
        if metrics_df.empty:
            return None
        cut = today - timedelta(days=days)
        vals = metrics_df[metrics_df["date"] >= cut][col].dropna()
        return round(float(vals.mean()), 1) if not vals.empty else None

    body_weight = metrics_series(metrics_df, "body_weight_kg") if not metrics_df.empty else {"summary": {}}

    top_groups = list(bal["by_group"].keys())[:3]
    bottom_groups = bal["undertrained"] or list(bal["by_group"].keys())[-3:]

    active_injuries = [i.body_part for i in user.injuries if i.healed_at is None]

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "workouts": {
            "this_week": _count_since(week_start),
            "this_month": _count_since(month_start),
            "in_range": 0 if sessions_df.empty else int(sessions_df["log_id"].nunique()),
            "current_streak_days": wc["current_streak_days"],
            "weekly_target": user.days_per_week,
            "adherence_pct": wc["adherence_pct"],
        },
        "training": {
            "total_activation_load": 0.0 if exercises_df.empty else round(float(exercises_df[MUSCLES].sum().sum()), 1),
            "total_sets": 0 if exercises_df.empty else int(exercises_df["sets"].sum()),
            "top_body_parts": top_groups,
            "undertrained_body_parts": bottom_groups,
            "push_pull_ratio": bal["push_pull_ratio"],
            "upper_lower_ratio": bal["upper_lower_ratio"],
        },
        "health": {
            "avg_steps_7d": _metric_avg("steps", 7),
            "avg_steps_30d": _metric_avg("steps", 30),
            "avg_active_calories_7d": _metric_avg("active_calories", 7),
            "avg_sleep_hours_7d": _metric_avg("sleep_hours", 7),
            "body_weight_change_kg": body_weight["summary"].get("change"),
            "latest_body_weight_kg": body_weight["summary"].get("latest"),
        },
        "readiness": _readiness(metrics_df, sessions_df, today),
        "injuries": {"active": active_injuries, "active_count": len(active_injuries)},
        "personal_records_enabled": user.show_personal_records,
    }


def _readiness(metrics_df: pd.DataFrame, sessions_df: pd.DataFrame, today: date) -> dict:
    """Rough 0-100 training-readiness score from recent sleep, energy rating, and
    days since last session. Heuristic, not medical."""
    score = 60.0
    reasons = []
    if not metrics_df.empty:
        recent = metrics_df[metrics_df["date"] >= today - timedelta(days=3)]
        sleep = recent["sleep_hours"].dropna()
        if not sleep.empty:
            avg = float(sleep.mean())
            score += (avg - 7) * 8
            reasons.append(f"3-day sleep avg {avg:.1f}h")
        energy = recent["energy_level"].dropna()
        if not energy.empty:
            avg_e = float(energy.mean())
            score += (avg_e - 3) * 6
            reasons.append(f"energy {avg_e:.1f}/5")
    if not sessions_df.empty:
        last = sessions_df["date"].max()
        gap = (today - last).days
        if gap <= 1:
            score -= 6
            reasons.append("trained in the last day")
        elif gap >= 3:
            score += 5
            reasons.append(f"{gap} days since last session")
    score = max(0, min(100, round(score)))
    label = "ready" if score >= 66 else "moderate" if score >= 45 else "hold back"
    return {"score": score, "label": label, "factors": reasons}


# ── PNG rendering ────────────────────────────────────────────────────────────

_ACCENT = "#3D7A00"


def _fig_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def png_muscle_heatmap(data: dict) -> bytes:
    cols, buckets, series = data["columns"], data["buckets"], data["series"]
    if not buckets:
        return _empty_png("No workout data in this range")
    frame = pd.DataFrame(series, index=buckets)[cols]
    frame.columns = [data["labels"].get(c, c) for c in cols]
    fig, ax = plt.subplots(figsize=(max(6, len(cols) * 0.42), max(3, len(buckets) * 0.4)))
    sns.heatmap(frame, cmap="YlGn", linewidths=0.5, linecolor="white", ax=ax,
                cbar_kws={"label": "activation-load" if data["normalize"] == "none" else "% of bucket"})
    ax.set_title(f"Muscle activation by {data['bucket']}", loc="left", fontweight="bold")
    ax.set_ylabel("")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    return _fig_png(fig)


def png_bar(labels: list, values: list, title: str, ylabel: str) -> bytes:
    if not labels:
        return _empty_png("No data in this range")
    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 0.6), 3.4))
    ax.bar(range(len(labels)), values, color=_ACCENT)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_png(fig)


def png_line(dates: list, values: list, rolling: list, title: str, ylabel: str) -> bytes:
    if not dates:
        return _empty_png("No data in this range")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(pd.to_datetime(dates), values, color="#9CC65B", lw=1, marker="o", ms=3, label="daily")
    if rolling:
        ax.plot(pd.to_datetime(dates), rolling, color=_ACCENT, lw=2.2, label="7-day avg")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    return _fig_png(fig)


def _empty_png(msg: str) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 2))
    ax.text(0.5, 0.5, msg, ha="center", va="center", color="#556070")
    ax.axis("off")
    return _fig_png(fig)


# ── Anatomical muscle map (SVG) ─────────────────────────────────────────────
#
# Fills real anatomical <path> regions (from body-muscles, Apache-2.0) with a
# colour scaled to that muscle's activation-load — so the shading lands inside
# the outline, not as blobs over a stick figure. Served as SVG: it renders
# crisply in a browser and is what the Stage 10 frontend will consume.

import html as _html  # noqa: E402

from app.data.muscle_map_paths import (  # noqa: E402
    BACK_REGIONS, FRONT_REGIONS, REGION_TO_MUSCLE, VIEWBOX,
)

# 6-stop ramp, low → high load. Light and dark variants (matched to the
# reference template's --int-* tokens).
_RAMP_LIGHT = ["#cdc8ba", "#cf9a4f", "#d97c2b", "#c4531f", "#a3301f", "#6e1616"]
_RAMP_DARK = ["#3a352d", "#8a6a37", "#c17d2e", "#c85a26", "#b3381f", "#7a1c1c"]
_SIL = {"light": "#cbc6b9", "dark": "#33302a"}
_INK = {"light": "#1c1a16", "dark": "#f1ede4"}
_MUTED = {"light": "#6f6a5f", "dark": "#9d968a"}
_SURFACE = {"light": "#ffffff", "dark": "#1b1916"}
_STROKE = {"light": "#b7b1a2", "dark": "#494236"}


def muscle_totals(exercises_df: pd.DataFrame) -> dict[str, float]:
    if exercises_df.empty:
        return {m: 0.0 for m in MUSCLES}
    return {m: round(float(exercises_df[m].sum()), 1) for m in MUSCLES}


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ramp(t: float, ramp: list[str]) -> str:
    """t in [0,1] -> interpolated colour across the ramp stops."""
    t = max(0.0, min(1.0, t))
    seg = t * (len(ramp) - 1)
    i = min(int(seg), len(ramp) - 2)
    f = seg - i
    a, b = _hex_rgb(ramp[i]), _hex_rgb(ramp[i + 1])
    return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))


def _regions_for(view: str) -> list[dict]:
    if view == "front":
        return FRONT_REGIONS
    if view == "back":
        return BACK_REGIONS
    return FRONT_REGIONS + BACK_REGIONS


def render_muscle_map_svg(
    totals: dict[str, float], title: str, subtitle: str, view: str = "both", theme: str = "auto",
) -> str:
    view = view if view in VIEWBOX else "both"
    themed = theme if theme in ("light", "dark") else "auto"
    vmax = max(totals.values()) if totals else 0.0

    x0, y0, w, h = (float(n) for n in VIEWBOX[view].split())
    pad_t, pad_b, pad_x = 11.0, 17.0, 3.0
    fx, fy, fw, fh = x0 - pad_x, y0 - pad_t, w + 2 * pad_x, h + pad_t + pad_b

    body: list[str] = [f'<rect class="mm-bg" x="{fx}" y="{fy}" width="{fw}" height="{fh}"/>']

    # flat silhouette under everything (incl. head / hands / feet / joints)
    body.append('<g>' + "".join(f'<path class="mm-sil" d="{r["path"]}"/>' for r in _regions_for(view)) + '</g>')

    # coloured muscle layer
    dark_rules: list[str] = []
    body.append('<g>')
    for i, reg in enumerate(_regions_for(view)):
        muscle = REGION_TO_MUSCLE.get(reg["id"])
        if muscle is None:
            continue  # left as silhouette
        t = (totals.get(muscle, 0.0) / vmax) if vmax > 0 else 0.0
        light, dark = _ramp(t, _RAMP_LIGHT), _ramp(t, _RAMP_DARK)
        fill = dark if themed == "dark" else light
        cls = f"mm-musc mmd{i}" if themed == "auto" else "mm-musc"
        name = _html.escape(MUSCLE_DISPLAY.get(muscle, {}).get("display_name", muscle))
        body.append(f'<path class="{cls}" fill="{fill}" d="{reg["path"]}">'
                    f'<title>{name}: {int(round(totals.get(muscle, 0.0)))}</title></path>')
        if themed == "auto":
            dark_rules.append(f".mmd{i}{{fill:{dark};}}")

    body.append('</g>')

    # captions
    if view == "both":
        body.append(f'<text class="mm-ink" x="{x0 + w * 0.25}" y="{y0 - 4}" font-size="3" '
                    f'font-weight="700" text-anchor="middle">Front</text>'
                    f'<text class="mm-ink" x="{x0 + w * 0.75}" y="{y0 - 4}" font-size="3" '
                    f'font-weight="700" text-anchor="middle">Back</text>')
    body.append(f'<text class="mm-ink" x="{fx + 1}" y="{fy + 4}" font-size="3.4" font-weight="800">'
                f'{_html.escape(title)}</text>'
                f'<text class="mm-muted" x="{fx + 1}" y="{fy + 8}" font-size="2.5">'
                f'{_html.escape(subtitle)}</text>')

    # legend + most-worked
    ly = y0 + h + 5.5
    ramp = _RAMP_DARK if themed == "dark" else _RAMP_LIGHT
    stops = "".join(f'<stop offset="{k / 5:.2f}" stop-color="{ramp[k]}"/>' for k in range(6))
    body.append(f'<defs><linearGradient id="mmg">{stops}</linearGradient></defs>'
                f'<rect x="{fx + 1}" y="{ly}" width="26" height="2.6" rx="1.3" fill="url(#mmg)"/>'
                f'<text class="mm-muted" x="{fx + 0.5}" y="{ly + 5.6}" font-size="2.1">low load</text>'
                f'<text class="mm-muted" x="{fx + 23}" y="{ly + 5.6}" font-size="2.1">peak</text>')
    top = [(MUSCLE_DISPLAY.get(m, {}).get("display_name", m), v)
           for m, v in sorted(totals.items(), key=lambda kv: -kv[1])[:5] if v > 0]
    if top:
        label = "Most worked:  " + "    ".join(f"{n} {int(round(v))}" for n, v in top)
        body.append(f'<text class="mm-ink" x="{fx + 1}" y="{ly + 11}" font-size="2.4" '
                    f'font-weight="600">{_html.escape(label)}</text>')

    light_vars = (f"--ink:{_INK['light']};--muted:{_MUTED['light']};--sil:{_SIL['light']};"
                  f"--surface:{_SURFACE['light']};--stroke:{_STROKE['light']};")
    dark_vars = (f"--ink:{_INK['dark']};--muted:{_MUTED['dark']};--sil:{_SIL['dark']};"
                 f"--surface:{_SURFACE['dark']};--stroke:{_STROKE['dark']};")
    root_vars = dark_vars if themed == "dark" else light_vars
    style = (
        f":root{{{root_vars}}}"
        ".mm-bg{fill:var(--surface);}"
        ".mm-sil{fill:var(--sil);stroke:var(--stroke);stroke-width:0.1;}"
        ".mm-musc{stroke:var(--stroke);stroke-width:0.15;}"
        ".mm-ink{fill:var(--ink);}.mm-muted{fill:var(--muted);}"
    )
    if themed == "auto":
        style += ("@media (prefers-color-scheme:dark){"
                  f":root{{{dark_vars}}}" + "".join(dark_rules) + "}")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{fx} {fy} {fw} {fh}" '
        f'font-family="ui-sans-serif,system-ui,-apple-system,sans-serif" role="img" '
        f'aria-label="{_html.escape(title)}"><style>{style}</style>'
        + "".join(body) + "</svg>"
    )
