"""
Demo seeder — run once before starting the server.

Creates three test users:
  • Tamir  — 24, intermediate, active right shoulder injury (all 4 suggestibility states)
  • Morgan — 30, beginner, no injuries — control user just starting a fitness journey
  • Jordan — 27, intermediate, minor left patellar tendon injury (mirrors Tamir's case for legs)

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
import app.models.daily_metric  # noqa — register all models
from app.database import Base as AppBase

AppBase.metadata.create_all(bind=engine)

NOW = datetime.now(timezone.utc)


def _ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


def seed_tamir(db) -> None:
    existing = db.query(_u.User).filter(_u.User.email == "tamir@demo.vectorfit").first()
    if existing:
        print(f"Tamir already exists (id={existing.id}) — skipping.")
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


def seed_control_user(db) -> None:
    """Morgan — 30, beginner, no injuries, no rejection history. A clean
    baseline for comparing against Tamir/Jordan: every exercise should come
    back ELIGIBLE, and the daily-program generator should never trigger a
    substitution/tooltip for this user."""
    existing = db.query(_u.User).filter(_u.User.email == "morgan@demo.vectorfit").first()
    if existing:
        print(f"Morgan already exists (id={existing.id}) — skipping.")
        return

    user = _u.User(
        name="Morgan",
        email="morgan@demo.vectorfit",
        age=30,
        weight_kg=70.0,
        height_cm=170.0,
        fitness_level="beginner",
        experience_level="beginner",
        days_per_week=3,
        minutes_per_session=30,
        goals_json=json.dumps(["general_fitness", "weight_loss"]),
        equipment_json=json.dumps(["bodyweight", "dumbbells"]),
        movement_preferences_json=json.dumps(["bodyweight", "free_weights"]),
        created_at=_ago(days=1),
        updated_at=_ago(days=1),
    )
    db.add(user)
    db.commit()

    print(f"""
Seeded successfully
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User:     Morgan  (id={user.id})  — control, no injuries, no history
Email:    morgan@demo.vectorfit
Goals:    general_fitness, weight_loss
Equipment: bodyweight, dumbbells only

Everything for this user should be ELIGIBLE — good baseline to diff against
Tamir/Jordan when checking that injury/preference filtering is actually doing
something (rather than every user just happening to look the same).
  GET /users/{user.id}/suggestibility/push_up   → should be ELIGIBLE
  POST /users/{user.id}/daily-program           → should show zero substitutions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def seed_leg_injury_user(db) -> None:
    """Jordan — 27, intermediate, minor left knee injury. Mirrors Tamir's
    shoulder case for the legs: against_gravity squat/lunge variants are
    blocked by force_direction, and leg_extension_machine (supported, but
    still knee_extension_under_load) is blocked via the joint-flag match —
    exercising both suppression paths independently."""
    existing = db.query(_u.User).filter(_u.User.email == "jordan@demo.vectorfit").first()
    if existing:
        print(f"Jordan already exists (id={existing.id}) — skipping.")
        return

    user = _u.User(
        name="Jordan",
        email="jordan@demo.vectorfit",
        age=27,
        weight_kg=68.0,
        height_cm=165.0,
        fitness_level="intermediate",
        experience_level="intermediate",
        days_per_week=4,
        minutes_per_session=45,
        goals_json=json.dumps(["strength", "muscle_gain"]),
        equipment_json=json.dumps(["dumbbells", "barbell", "squat_rack", "bench", "machines"]),
        movement_preferences_json=json.dumps(["free_weights", "machines"]),
        created_at=_ago(days=10),
        updated_at=_ago(days=10),
    )
    db.add(user)
    db.flush()

    knee = _u.Injury(
        user_id=user.id,
        # Deliberately "patellar tendon", not "knee" — flags_for_body_part()
        # does substring matching, and the generic "knee" keyword implies a
        # broader flag set (including knee_flexion_under_load) that would also
        # suppress leg_press, defeating the point of it as the safe substitute.
        body_part="left patellar tendon",
        severity="mild",
        pain_type="dull_stiff",
        recovery_expectation_days=14,
        notes=(
            "Mild patellar tendon irritation. Avoid deep bodyweight-loaded knee "
            "flexion (squats, lunges, jumps) and open-chain knee extension under "
            "load (leg extension machine). Leg press and hack squat machine are "
            "fine with light-moderate load."
        ),
        healed_at=None,
        is_active=True,
        restricted_force_directions_json=json.dumps(["against_gravity"]),
        created_at=_ago(days=4),
        updated_at=_ago(days=4),
    )
    db.add(knee)

    rejections = [
        # bench press: too_sore 1 day ago → COOLDOWN. Deliberately not a leg
        # exercise — anything against_gravity or knee-flagged is already
        # SUPPRESSED by the injury, and suppression outranks cooldown, so an
        # overlapping pick would never actually surface COOLDOWN.
        RejectionEvent(
            user_id=user.id,
            exercise_id="barbell_bench_press",
            exercise_name="Barbell Bench Press",
            reason="too_sore",
            pain_level=2,
            body_area="chest",
            note="Chest still fatigued from yesterday's session",
            created_at=_ago(days=1),
        ),
        # barbell_curl: dont_like → PREFERENCE_PENALIZED
        RejectionEvent(
            user_id=user.id,
            exercise_id="barbell_curl",
            exercise_name="Barbell Curl",
            reason="dont_like",
            note="Never feels like it's doing much",
            created_at=_ago(days=6),
        ),
    ]
    for r in rejections:
        db.add(r)
    db.commit()

    print(f"""
Seeded successfully
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User:     Jordan  (id={user.id})
Email:    jordan@demo.vectorfit
Injury:   left patellar tendon, mild — active since 4 days ago
          restricted: against_gravity force direction

Suggestibility states to demo:
  barbell_back_squat     → SUPPRESSED  (force_direction: against_gravity)
  lunge                  → SUPPRESSED  (force_direction: against_gravity)
  leg_extension_machine  → SUPPRESSED  (joint flag: knee_extension_under_load — supported, so
                                        this one only trips via the flag match, not force_direction)
  leg_press              → ELIGIBLE    (supported, no knee_extension/valgus flag — the safe swap)
  barbell_bench_press    → COOLDOWN    (too_sore 1 day ago, clears in 2 days)
  barbell_curl           → PREFERENCE_PENALIZED  (dont_like, score=0.85)

Try these in /docs (replace {user.id} with the user id above):
  GET /users/{user.id}/suggestibility/barbell_back_squat
  GET /users/{user.id}/suggestibility/leg_extension_machine
  GET /users/{user.id}/substitute/barbell_back_squat
  GET /users/{user.id}/explain/barbell_back_squat
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def seed_custom_workout(db) -> None:
    """One custom-builder template for Morgan — a starting point for Stage 8
    endpoint testing (edit exercises, reorder, analyse, start, complete)."""
    from app.models.workout_log import WorkoutExercise, WorkoutLog

    morgan = db.query(_u.User).filter(_u.User.email == "morgan@demo.vectorfit").first()
    if not morgan:
        return
    if db.query(WorkoutLog).filter(WorkoutLog.user_id == morgan.id, WorkoutLog.source == "custom_builder").first():
        print("Custom workout already exists for Morgan — skipping.")
        return

    tmpl = WorkoutLog(
        user_id=morgan.id,
        name="Morgan's Full Body A",
        workout_type="full_body",
        source="custom_builder",
        is_template=True,
        notes="Twice a week, alternate with Full Body B.",
        started_at=_ago(days=1),
    )
    picks = [
        ("goblet_squat", 3, "8-12", None, "Dumbbell at chest, sit between the heels."),
        ("dumbbell_bench_press", 3, "8-12", None, None),
        ("dumbbell_row", 3, "10-12", None, "Each side."),
        ("romanian_deadlift_dumbbell", 3, "10-12", None, "Soft knees, hinge from the hips."),
        ("plank", 3, None, 45, "Hold, ribs down."),
    ]
    for pos, (ex_id, sets, reps, dur, note) in enumerate(picks):
        tmpl.exercises.append(WorkoutExercise(
            exercise_id=ex_id, exercise_name=ex_id.replace("_", " ").title(),
            position=pos, sets=sets, reps=reps, duration_seconds=dur,
            rest_seconds=60, notes=note,
        ))
    db.add(tmpl)
    db.commit()
    print(f"""
Seeded custom workout template
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workout:  "Morgan's Full Body A"  (template, user id={morgan.id})
Try:
  GET  /users/{morgan.id}/workouts
  GET  /users/{morgan.id}/workouts/{{wid}}/suggestions?body_part=back&facets=true
  GET  /users/{morgan.id}/workouts/{{wid}}/analysis
  POST /users/{morgan.id}/workouts/{{wid}}/start
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def seed_history(db) -> None:
    """~8 weeks of completed workouts + daily health metrics for all three demo
    users, so the Stage 9 dashboard has something to chart. Distinct shapes:
      • Tamir  — steady 3x/week, trains around the shoulder (pull / full body / core)
      • Morgan — ramps up: 1–2x/week early, 3x/week recently
      • Jordan — 4x/week, a volume dip in the week around his injury, then recovery
    """
    import random
    from app.models.daily_metric import DailyMetric
    from app.models.workout_log import WorkoutExercise, WorkoutLog

    rng = random.Random(42)
    dataset = json.load(open(Path(__file__).parent / "exercises.json", encoding="utf-8"))["exercises"]
    by_pattern: dict[str, list[dict]] = {}
    for ex in dataset:
        by_pattern.setdefault(ex["movement_pattern"], []).append(ex)

    _TYPE_PATTERNS = {
        "push": ["push"], "pull": ["pull"], "legs": ["squat", "hinge"],
        "upper": ["push", "pull"], "full_body": ["push", "pull", "squat", "hinge"],
        "core_and_carry": ["core", "carry"],
    }
    _WEIGHTED_EQUIP = {"barbell", "dumbbells", "kettlebell", "cables", "machines"}

    ex_base_weight: dict[tuple[int, str], float] = {}

    def pick_exercises(user_id: int, wtype: str, equipment: set[str], n: int, week: int) -> list[dict]:
        equip = equipment | {"bodyweight"}
        pool: list[dict] = []
        for pat in _TYPE_PATTERNS[wtype]:
            cands = [e for e in by_pattern.get(pat, []) if set(e.get("equipment_required", [])) <= equip]
            cands.sort(key=lambda e: -sum(e["muscle_activation"].values()))
            pool.extend(cands[:8])
        rng.shuffle(pool)
        out = []
        for e in pool[:n]:
            weighted = bool(set(e.get("equipment_required", [])) & _WEIGHTED_EQUIP)
            weight = None
            if weighted:
                key = (user_id, e["id"])
                base = ex_base_weight.setdefault(key, rng.choice([15, 20, 25, 30, 40, 50, 60]))
                # steady linear progression + a little session-to-session noise
                weight = round(base * (1 + 0.01 * week) + rng.uniform(-1.5, 1.5), 1)
            out.append({"ex": e, "weight": weight})
        return out

    # Exercises the injury engine would have swapped out, per user — used to
    # populate a few realistic substitutions so the dashboard's "safety engine
    # at work" panel has data.
    _SWAPPED_OUT = {
        "Tamir":  [("overhead_press", "Overhead Press (Military Press)"),
                   ("push_up", "Push-up"), ("pull_up", "Pull-up")],
        "Jordan": [("barbell_back_squat", "Barbell Back Squat"),
                   ("lunge", "Lunge"), ("leg_extension_machine", "Leg Extension Machine")],
    }

    def make_workout(user, d, wtype, week):
        equipment = set(user.equipment)
        picks = pick_exercises(user.id, wtype, equipment, rng.randint(4, 6), week)
        started = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc).replace(hour=18)
        log = WorkoutLog(
            user_id=user.id, name=None, workout_type=wtype, source="daily",
            is_template=False, started_at=started,
            completed_at=started + timedelta(minutes=rng.randint(38, 62)),
        )
        swaps = _SWAPPED_OUT.get(user.name, [])
        swap_here = swaps and rng.random() < 0.3
        for pos, p in enumerate(picks):
            sub_for_id = sub_for_name = None
            if swap_here and pos == 0:
                sub_for_id, sub_for_name = rng.choice(swaps)
            log.exercises.append(WorkoutExercise(
                exercise_id=p["ex"]["id"], exercise_name=p["ex"]["name"], position=pos,
                sets=rng.randint(3, 4), reps=rng.choice(["6-8", "8-10", "8-12", "10-12"]),
                rest_seconds=rng.choice([60, 75, 90]), weight_kg=p["weight"],
                feedback=rng.choice([None, None, None, "liked"]),
                substituted_for_id=sub_for_id, substituted_for_name=sub_for_name,
                substitution_note=(f"{sub_for_name} was swapped out for a safer alternative."
                                   if sub_for_name else None),
            ))
        db.add(log)

    users = {u.name: u for u in db.query(_u.User).all()}
    if db.query(WorkoutLog).filter(WorkoutLog.source == "daily").first():
        print("Workout history already seeded — skipping.")
        return

    NWEEKS = 13
    plans = {
        # per_week takes weeks_ago (0 = current week)
        "Tamir":  (["pull", "full_body", "core_and_carry"], lambda ago: 3),
        "Morgan": (["full_body", "upper", "legs"], lambda ago: 1 if ago > 9 else (2 if ago > 5 else 3)),
        "Jordan": (["legs", "push", "pull", "upper"], lambda ago: 2 if ago == 1 else 4),
    }

    for name, (rotation, per_week) in plans.items():
        user = users.get(name)
        if not user:
            continue
        rot_i = 0
        for week in range(NWEEKS):  # 0 = oldest, NWEEKS-1 = current week
            weeks_ago = NWEEKS - 1 - week
            train_days = rng.sample(range(7), k=min(per_week(weeks_ago), 7))
            for dow in sorted(train_days):
                days_ago = weeks_ago * 7 + (6 - dow)
                if days_ago < 0:
                    continue
                d = (NOW - timedelta(days=days_ago)).date()
                make_workout(user, d, rotation[rot_i % len(rotation)], week)
                rot_i += 1

    # ── Daily health metrics — last 95 days ─────────────────────────────────
    weight_base = {"Tamir": 78.0, "Morgan": 70.0, "Jordan": 68.0}
    for name, user in users.items():
        if name not in weight_base:
            continue
        w = weight_base[name]
        for days_ago in range(95, -1, -1):
            d = (NOW - timedelta(days=days_ago)).date()
            weekday = d.weekday()
            steps = int(rng.gauss(8500 if weekday < 5 else 6500, 1800))
            steps = max(1500, steps)
            trained = db.query(WorkoutLog).filter(
                WorkoutLog.user_id == user.id, WorkoutLog.source == "daily",
                WorkoutLog.started_at >= datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc),
                WorkoutLog.started_at < datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
            ).first() is not None
            w += rng.gauss(-0.02 if name != "Morgan" else -0.05, 0.15)  # slight downward drift
            db.add(DailyMetric(
                user_id=user.id, date=d,
                steps=steps,
                active_calories=int(steps * 0.035 + (rng.randint(180, 320) if trained else 0)),
                resting_heart_rate=int(rng.gauss(58, 3)),
                body_weight_kg=round(w, 1),
                sleep_hours=round(max(4.5, min(9.0, rng.gauss(7.1, 0.8))), 1),
                energy_level=rng.choice([2, 3, 3, 4, 4, 5]),
            ))

    db.commit()
    n_logs = db.query(WorkoutLog).filter(WorkoutLog.source == "daily").count()
    print(f"""
Seeded workout history + health metrics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{n_logs} completed workouts across Tamir / Morgan / Jordan, ~13 weeks back.
96 days of daily metrics (steps, calories, weight, sleep, RHR, energy) each.
Try:
  GET /users/1/dashboard/summary
  GET /users/1/dashboard/muscle-activation?bucket=week&group=body_part&format=png
  GET /users/3/dashboard/workouts?format=png
  GET /users/1/dashboard/metrics?metric=steps&format=png
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_tamir(db)
        seed_control_user(db)
        seed_leg_injury_user(db)
        seed_custom_workout(db)
        seed_history(db)
    finally:
        db.close()
