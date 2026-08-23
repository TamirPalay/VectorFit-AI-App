"""
Demo seeder — run once before starting the server.

Creates:
  • 1 user  — Tamir, 24, right shoulder injury
  • 1 active right shoulder injury (suppresses push_up, overhead_press)
  • 5 rejection events covering all four suggestibility states

Usage (from backend/ directory):
    python -m app.data.seed_demo
"""

import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.database import SessionLocal, engine
from app.models import user as _u
from app.models.rejection import RejectionEvent
import app.models.workout_log  # noqa — register all models
from app.database import Base as AppBase

AppBase.metadata.create_all(bind=engine)

NOW = datetime.now(timezone.utc)


def _ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


def seed(db) -> None:
    existing = db.query(_u.User).filter(_u.User.email == "tamir@demo.vectorfit").first()
    if existing:
        print(f"Demo user already exists (id={existing.id}) — skipping seed.")
        print("To re-seed: delete vectorfit.db and run again.")
        return

    # ── User ──────────────────────────────────────────────────────────────────
    user = _u.User(
        name="Tamir",
        email="tamir@demo.vectorfit",
        age=24,
        weight_kg=75.0,
        height_cm=180.0,
        fitness_level="intermediate",
        experience_level="intermediate",
        days_per_week=4,
        minutes_per_session=45,
        goals_json=json.dumps(["fitness", "health", "recovery"]),
        # Has resistance bands at home; barbell/machines when at the gym
        equipment_json=json.dumps(["resistance_bands", "dumbbells", "barbell", "cables", "pull_up_bar"]),
        movement_preferences_json=json.dumps(["free_weights", "resistance_bands"]),
        created_at=_ago(days=14),
        updated_at=_ago(days=14),
    )
    db.add(user)
    db.flush()

    # ── Active injury: right shoulder ──────────────────────────────────────────
    # • Suppresses any exercise whose joint_stress_flags overlap shoulder flags
    # • Also restricts force_direction="against_gravity" (no push-up position)
    shoulder = _u.Injury(
        user_id=user.id,
        body_part="right shoulder",
        severity="moderate",
        pain_type="sharp_acute",
        recovery_expectation_days=21,
        notes=(
            "Rotator cuff strain. Physio says avoid overhead loading and "
            "bodyweight-bearing positions (push-up, dip). Bench press with "
            "controlled weight is fine."
        ),
        healed_at=None,
        is_active=True,
        restricted_force_directions_json=json.dumps(["against_gravity"]),
        created_at=_ago(days=7),
        updated_at=_ago(days=7),
    )
    db.add(shoulder)

    # ── Rejection events ───────────────────────────────────────────────────────
    # Demonstrates all four suggestibility states:
    #
    #  push_up            → SUPPRESSED (injury)
    #  overhead_press     → SUPPRESSED (injury) + PREFERENCE_PENALIZED
    #  pull_up            → COOLDOWN   (too_sore 1 day ago — still in 3-day window)
    #  barbell_curl       → PREFERENCE_PENALIZED (too_easy)
    #  plank              → PREFERENCE_PENALIZED (too_hard)
    #  barbell_back_squat → ELIGIBLE   (too_sore 10 days ago — cooldown long expired)
    #  barbell_bench_press → ELIGIBLE  (no rejections, no injury conflict)

    rejections = [
        # pull_up: too_sore 1 day ago → COOLDOWN (3-day window, clears day after tomorrow)
        RejectionEvent(
            user_id=user.id,
            exercise_id="pull_up",
            exercise_name="Pull-up",
            reason="too_sore",
            pain_level=5,
            pain_type="dull_stiff",
            body_area="lats",
            note="Heavy lat session yesterday — can't hang on the bar today",
            created_at=_ago(days=1),
        ),
        # lat_pulldown: not_today → COOLDOWN (1-day soft skip, no preference hit)
        RejectionEvent(
            user_id=user.id,
            exercise_id="lat_pulldown",
            exercise_name="Lat Pulldown",
            reason="not_today",
            note="Just not feeling it — skipping for now",
            created_at=_ago(hours=3),
        ),
        # overhead_press: dont_like ×2 → PREFERENCE_PENALIZED (score=0.70, also SUPPRESSED by injury)
        RejectionEvent(
            user_id=user.id,
            exercise_id="overhead_press",
            exercise_name="Overhead Press (Military Press)",
            reason="dont_like",
            created_at=_ago(days=5),
        ),
        RejectionEvent(
            user_id=user.id,
            exercise_id="overhead_press",
            exercise_name="Overhead Press (Military Press)",
            reason="dont_like",
            created_at=_ago(days=12),
        ),
        # barbell_curl: too_easy → PREFERENCE_PENALIZED (score=0.90)
        RejectionEvent(
            user_id=user.id,
            exercise_id="barbell_curl",
            exercise_name="Barbell Curl",
            reason="too_easy",
            created_at=_ago(days=3),
        ),
        # plank: too_hard → PREFERENCE_PENALIZED (score=0.90)
        RejectionEvent(
            user_id=user.id,
            exercise_id="plank",
            exercise_name="Plank",
            reason="too_hard",
            created_at=_ago(days=6),
        ),
        # barbell_back_squat: too_sore 10 days ago → ELIGIBLE (cooldown long expired)
        RejectionEvent(
            user_id=user.id,
            exercise_id="barbell_back_squat",
            exercise_name="Barbell Back Squat",
            reason="too_sore",
            pain_level=3,
            body_area="quads",
            created_at=_ago(days=10),
        ),
        # dumbbell_shoulder_press: bad_form → PREFERENCE_PENALIZED (score=0.92, also SUPPRESSED)
        RejectionEvent(
            user_id=user.id,
            exercise_id="dumbbell_shoulder_press",
            exercise_name="Dumbbell Shoulder Press",
            reason="bad_form",
            note="Can't keep my right shoulder stable — form breaks down at heavier weights",
            created_at=_ago(days=4),
        ),
        # romanian_deadlift (if exists): too_long → PREFERENCE_PENALIZED (score=0.95)
        RejectionEvent(
            user_id=user.id,
            exercise_id="barbell_bench_press",
            exercise_name="Barbell Bench Press",
            reason="too_long",
            note="Takes forever to set up the rack — no time today",
            created_at=_ago(days=8),
        ),
    ]

    for r in rejections:
        db.add(r)
    db.commit()

    uid = user.id
    print(f"""
Seeded successfully
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User:     Tamir  (id={uid})
Email:    tamir@demo.vectorfit
Injury:   right shoulder, moderate — active since 7 days ago
          restricted: against_gravity force direction

Suggestibility states to demo:
  push_up               → SUPPRESSED           (injury, against_gravity)
  overhead_press        → SUPPRESSED           (injury + dont_like ×2, score=0.70)
  dumbbell_shoulder_press → SUPPRESSED         (injury + bad_form penalty)
  pull_up               → COOLDOWN             (too_sore 1 day ago, clears in 2 days)
  lat_pulldown          → COOLDOWN             (not_today 3 hrs ago, clears tomorrow)
  barbell_curl          → PREFERENCE_PENALIZED  (too_easy, score=0.90)
  plank                 → PREFERENCE_PENALIZED  (too_hard, score=0.90)
  barbell_bench_press   → PREFERENCE_PENALIZED  (too_long, score=0.95)
  barbell_back_squat    → ELIGIBLE             (old soreness, cooldown expired)

Try these in /docs (replace {uid} with the user id above):
  GET /users/{uid}/suggestibility/push_up
  GET /users/{uid}/suggestibility/barbell_bench_press
  GET /users/{uid}/suggestibility/pull_up
  GET /users/{uid}/substitute/push_up
  GET /users/{uid}/substitute/pull_up
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
