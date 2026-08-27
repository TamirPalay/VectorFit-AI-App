"""
Daily / weekly program generator — Stage 7.

Flow per day: build a "generic" exercise plan for a workout type (ignoring
injuries — what anyone with this equipment/goal profile would get), then run
it through SuggestibilityEngine. Anything SUPPRESSED or COOLDOWN gets swapped
via SubstitutionEngine, and the swap is explained via explanation_service so
the frontend can show a tooltip: "X was swapped out for Y, here's why."
PREFERENCE_PENALIZED exercises stay in — that state is never a hard block.

Workout-type selection is NOT a fixed round robin. Each day/slot is scored
from the user's goals, equipment, rejection history (which movement patterns
they tend to push back on), and recent training volume per movement pattern
(so e.g. two leg-heavy days rarely land back to back). All of this is
deterministic Python — the LLM is only ever used to narrate a swap, never to
decide what's safe or what to train, consistent with Stages 4-6.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ml.embeddings import ExerciseIndex, cosine_similarity
from app.models.rejection import RejectionEvent
from app.models.user import User
from app.models.workout_log import WorkoutExercise, WorkoutLog
from app.services.explanation_service import explain_substitutions_batch
from app.services.suggestibility_engine import (
    SuggestibilityEngine,
    SuggestibilityState,
    compute_preference_score,
)
from app.services.substitution_engine import SubstitutionEngine

WORKOUT_TYPES: dict[str, dict] = {
    "push":           {"label": "Push",              "patterns": ["push"]},
    "pull":           {"label": "Pull",               "patterns": ["pull"]},
    "legs":           {"label": "Legs",                "patterns": ["squat", "hinge"]},
    "upper":          {"label": "Upper Body",          "patterns": ["push", "pull"]},
    "full_body":      {"label": "Full Body",           "patterns": ["push", "pull", "squat", "hinge"]},
    "core_and_carry": {"label": "Core & Conditioning", "patterns": ["core", "carry"]},
}

_RECENCY_LOOKBACK_DAYS = 5
_MINUTES_PER_EXERCISE = 6  # rough: work sets + rest, used to size the session
_NEAR_DUPLICATE_SIMILARITY = 0.93  # within a pattern, skip exercises this close to one already picked

# Weight each workout type gets per goal (1.0 = neutral). Keyed on schemas.user.VALID_GOALS.
_GOAL_TYPE_AFFINITY: dict[str, dict[str, float] | str] = {
    "strength":        {"push": 1.1, "pull": 1.1, "legs": 1.2, "upper": 0.6, "full_body": 0.5, "core_and_carry": 0.5},
    "muscle_gain":     {"push": 1.2, "pull": 1.2, "legs": 1.1, "upper": 0.6, "full_body": 0.4, "core_and_carry": 0.5},
    "hypertrophy":     {"push": 1.2, "pull": 1.2, "legs": 1.1, "upper": 0.6, "full_body": 0.4, "core_and_carry": 0.5},
    "endurance":       {"push": 0.7, "pull": 0.7, "legs": 0.9, "upper": 0.8, "full_body": 1.2, "core_and_carry": 1.1},
    "mobility":        {"push": 0.5, "pull": 0.5, "legs": 0.6, "upper": 0.6, "full_body": 1.0, "core_and_carry": 1.3},
    "general_fitness": {"push": 0.8, "pull": 0.8, "legs": 0.8, "upper": 0.9, "full_body": 1.2, "core_and_carry": 1.0},
    "sport_specific":  {"push": 0.9, "pull": 0.9, "legs": 1.0, "upper": 0.8, "full_body": 1.1, "core_and_carry": 1.1},
    "weight_loss":     {"push": 0.7, "pull": 0.7, "legs": 0.8, "upper": 0.7, "full_body": 1.3, "core_and_carry": 1.1},
    "recovery":        {"push": 0.3, "pull": 0.3, "legs": 0.3, "upper": 0.4, "full_body": 1.2, "core_and_carry": 1.2},
    # Aliases seen in seed/demo data that don't match the canonical VALID_GOALS taxonomy.
    "fitness": "general_fitness",
    "health": "general_fitness",
}

_VOLUME_BY_LEVEL = {
    "beginner":     {"sets": 3, "reps": "10-12", "rest": 60},
    "intermediate": {"sets": 3, "reps": "8-12", "rest": 75},
    "advanced":     {"sets": 4, "reps": "6-10", "rest": 90},
}


@dataclass
class ExerciseSlot:
    exercise: dict
    substituted_for: dict | None = None
    substitution_note: str | None = None


@dataclass
class DayPlan:
    day_index: int
    date: date
    is_rest: bool
    workout_type: str | None = None
    workout_label: str | None = None
    slots: list[ExerciseSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DailyProgramEngine:
    def __init__(self, db: Session, index: ExerciseIndex) -> None:
        self._db = db
        self._index = index
        self._suggestibility = SuggestibilityEngine(db)
        self._substitution = SubstitutionEngine(db=db, index=index)
        # (original_id, substitute_id) -> narration. Reused across days within a
        # single generate_week() call so an identical swap is narrated once, not
        # once per day. Seeded from previously-persisted notes on first lookup.
        self._note_cache: dict[tuple[str, str], str] = {}

    # ── History reads ────────────────────────────────────────────────────

    def _recent_pattern_volume(self, user_id: int, before: date) -> dict[str, float]:
        """Recency-weighted count of sessions per movement pattern in the last
        few days (yesterday counts full, older days decay to 0 at the lookback
        edge). Only counts logs strictly before `before` — a pre-generated
        future week must never count as "recent training"."""
        today_dt = datetime.combine(before, datetime.min.time(), tzinfo=timezone.utc)
        since = today_dt - timedelta(days=_RECENCY_LOOKBACK_DAYS)
        logs = (
            self._db.query(WorkoutLog)
            .filter(WorkoutLog.user_id == user_id, WorkoutLog.started_at >= since, WorkoutLog.started_at < today_dt)
            .all()
        )
        volume: dict[str, float] = defaultdict(float)
        for log in logs:
            started = log.started_at if log.started_at.tzinfo else log.started_at.replace(tzinfo=timezone.utc)
            days_ago = max(0, (today_dt - started).days)
            weight = max(0.0, 1 - days_ago / _RECENCY_LOOKBACK_DAYS)
            if weight == 0:
                continue
            for we in log.exercises:
                ex = self._index.get_by_id(we.exercise_id)
                if ex is not None:
                    volume[ex["movement_pattern"]] += weight
        return volume

    def _recent_exercise_ids(self, user_id: int, before: date) -> set[str]:
        today_dt = datetime.combine(before, datetime.min.time(), tzinfo=timezone.utc)
        since = today_dt - timedelta(days=_RECENCY_LOOKBACK_DAYS)
        logs = (
            self._db.query(WorkoutLog)
            .filter(WorkoutLog.user_id == user_id, WorkoutLog.started_at >= since, WorkoutLog.started_at < today_dt)
            .all()
        )
        return {we.exercise_id for log in logs for we in log.exercises}

    def _pattern_preference_avg(self, user_id: int) -> dict[str, float]:
        """Average preference score per movement pattern, from the user's full
        rejection history — deprioritizes (never hard-blocks) patterns the user
        consistently pushes back on."""
        rejections = self._db.query(RejectionEvent).filter(RejectionEvent.user_id == user_id).all()
        by_pattern: dict[str, list] = defaultdict(list)
        for r in rejections:
            ex = self._index.get_by_id(r.exercise_id)
            if ex is not None:
                by_pattern[ex["movement_pattern"]].append(r)
        return {p: compute_preference_score(rs) for p, rs in by_pattern.items()}

    def _equipment_fit(self, user: User) -> dict[str, float]:
        equipment = set(user.equipment) | {"bodyweight"}
        totals: dict[str, int] = defaultdict(int)
        available: dict[str, int] = defaultdict(int)
        for ex in self._index.all_exercises():
            p = ex["movement_pattern"]
            totals[p] += 1
            if set(ex.get("equipment_required", [])) <= equipment:
                available[p] += 1

        fit: dict[str, float] = {}
        for type_name, cfg in WORKOUT_TYPES.items():
            pattern_fits = [available[p] / totals[p] for p in cfg["patterns"] if totals[p]]
            fit[type_name] = max(0.1, sum(pattern_fits) / len(pattern_fits)) if pattern_fits else 0.1
        return fit

    def _pattern_viability(self, user: User) -> dict[str, float]:
        """Fraction of this user's equipment-fit exercises in each movement
        pattern that survive suggestibility (i.e. aren't SUPPRESSED/COOLDOWN).
        Lets type scoring avoid scheduling, say, a legs day for someone whose
        injury blocks nearly every squat/hinge — the generator would otherwise
        swap out the entire session. Computed once per generation."""
        equipment = set(user.equipment) | {"bodyweight"}
        by_pattern: dict[str, list[dict]] = defaultdict(list)
        for ex in self._index.all_exercises():
            if set(ex.get("equipment_required", [])) <= equipment:
                by_pattern[ex["movement_pattern"]].append(ex)

        viability: dict[str, float] = {}
        for pattern, exs in by_pattern.items():
            sample = sorted(exs, key=lambda e: -self._activation_magnitude(e))[:15]
            if not sample:
                viability[pattern] = 0.0
                continue
            results = self._suggestibility.batch_compute(user.id, sample)
            blocked = sum(
                1 for r in results
                if r.state in (SuggestibilityState.SUPPRESSED, SuggestibilityState.COOLDOWN)
            )
            viability[pattern] = 1 - blocked / len(sample)
        return viability

    def _last_workout_type(self, user_id: int, before: date) -> str | None:
        today_dt = datetime.combine(before, datetime.min.time(), tzinfo=timezone.utc)
        log = (
            self._db.query(WorkoutLog)
            .filter(WorkoutLog.user_id == user_id, WorkoutLog.source == "daily", WorkoutLog.started_at < today_dt)
            .order_by(WorkoutLog.started_at.desc())
            .first()
        )
        return log.workout_type if log else None

    def _trained_days_this_calendar_week(self, user_id: int, d: date) -> int:
        week_start = d - timedelta(days=d.weekday())  # Monday
        start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        return (
            self._db.query(WorkoutLog)
            .filter(
                WorkoutLog.user_id == user_id,
                WorkoutLog.source == "daily",
                WorkoutLog.started_at >= start,
                WorkoutLog.started_at < end,
            )
            .count()
        )

    # ── Workout-type scoring (replaces a fixed rotation) ────────────────

    def _goal_affinity(self, goals: list[str], type_name: str) -> float:
        if not goals:
            return 1.0
        scores = []
        for g in goals:
            entry = _GOAL_TYPE_AFFINITY.get(g)
            if isinstance(entry, str):  # alias -> canonical goal
                entry = _GOAL_TYPE_AFFINITY.get(entry)
            scores.append(entry.get(type_name, 1.0) if entry else 1.0)
        return sum(scores) / len(scores)

    def _score_type(
        self,
        type_name: str,
        user: User,
        recent_volume: dict[str, float],
        pattern_pref: dict[str, float],
        equip_fit: dict[str, float],
        pattern_viability: dict[str, float],
        prev_type: str | None,
        used_this_week: dict[str, int],
    ) -> float:
        patterns = WORKOUT_TYPES[type_name]["patterns"]

        score = self._goal_affinity(user.goals, type_name)
        score *= equip_fit.get(type_name, 0.5)

        # Steer away from types the user's injuries would gut (min across the
        # type's patterns — one fully-blocked pattern sinks the whole type).
        viability = min((pattern_viability.get(p, 1.0) for p in patterns), default=1.0)
        score *= 0.1 + 0.9 * viability

        recency_load = sum(recent_volume.get(p, 0.0) for p in patterns)
        score *= max(0.15, 1 - 0.15 * recency_load)

        pref_avg = sum(pattern_pref.get(p, 1.0) for p in patterns) / len(patterns)
        score *= 0.5 + 0.5 * pref_avg

        if prev_type == type_name and type_name != "full_body":
            score *= 0.3  # discourage repeating yesterday's type, full_body excepted

        score *= 0.75 ** used_this_week.get(type_name, 0)  # diminishing returns within a week
        return score

    def _choose_type(
        self,
        user: User,
        recent_volume: dict[str, float],
        pattern_pref: dict[str, float],
        equip_fit: dict[str, float],
        pattern_viability: dict[str, float],
        prev_type: str | None,
        used_this_week: dict[str, int],
    ) -> str:
        scored = {
            t: self._score_type(
                t, user, recent_volume, pattern_pref, equip_fit, pattern_viability, prev_type, used_this_week
            )
            for t in WORKOUT_TYPES
        }
        return max(scored, key=scored.get)

    def resolve_day_type(self, user: User, target_date: date) -> str | None:
        """For a single ad-hoc day (not a week batch): rest if the user has
        already hit their weekly training-day quota this calendar week,
        otherwise the best-scoring type given real history."""
        if self._trained_days_this_calendar_week(user.id, target_date) >= user.days_per_week:
            return None
        return self._choose_type(
            user,
            recent_volume=self._recent_pattern_volume(user.id, target_date),
            pattern_pref=self._pattern_preference_avg(user.id),
            equip_fit=self._equipment_fit(user),
            pattern_viability=self._pattern_viability(user),
            prev_type=self._last_workout_type(user.id, target_date),
            used_this_week={},
        )

    def _rest_day_indices(self, days_per_week: int) -> set[int]:
        training_days = max(0, min(days_per_week, 7))
        rest_days = 7 - training_days
        if rest_days <= 0:
            return set()
        interval = 7 / rest_days
        return {round(i * interval) % 7 for i in range(rest_days)}

    def _plan_week_types(self, user: User, start_date: date) -> list[str | None]:
        """Lay out the next 7 days (rolling from start_date, not calendar-aligned)."""
        rest_indices = self._rest_day_indices(user.days_per_week)
        recent_volume = self._recent_pattern_volume(user.id, start_date)
        pattern_pref = self._pattern_preference_avg(user.id)
        equip_fit = self._equipment_fit(user)
        pattern_viability = self._pattern_viability(user)

        plan: list[str | None] = []
        used_this_week: dict[str, int] = defaultdict(int)
        prev_type: str | None = self._last_workout_type(user.id, start_date)

        for day_index in range(7):
            if day_index in rest_indices:
                plan.append(None)
                prev_type = None  # a rest day resets the "avoid repeating yesterday" penalty
                continue

            chosen = self._choose_type(
                user, recent_volume, pattern_pref, equip_fit, pattern_viability, prev_type, used_this_week
            )
            plan.append(chosen)
            used_this_week[chosen] += 1
            prev_type = chosen

            # Feed this day's patterns forward so later days in the same batch
            # are scored as if this session already happened.
            for p in WORKOUT_TYPES[chosen]["patterns"]:
                recent_volume[p] = recent_volume.get(p, 0.0) + 1.0

        return plan

    # ── Exercise selection within a day ─────────────────────────────────

    @staticmethod
    def _activation_magnitude(ex: dict) -> float:
        return sum(ex.get("muscle_activation", {}).values())

    def _exercise_count(self, user: User) -> int:
        return max(3, round(user.minutes_per_session / _MINUTES_PER_EXERCISE))

    def _select_generic_exercises(
        self, user: User, patterns: list[str], exercise_count: int, recent_exercise_ids: set[str]
    ) -> list[dict]:
        """The 'generic' plan: what this equipment/goal profile would get,
        ignoring injuries entirely. Suggestibility is applied afterward."""
        equipment = set(user.equipment) | {"bodyweight"}
        per_pattern = max(1, round(exercise_count / len(patterns)))

        chosen: list[dict] = []
        for pattern in patterns:
            candidates = [
                ex for ex in self._index.all_exercises()
                if ex["movement_pattern"] == pattern and set(ex.get("equipment_required", [])) <= equipment
            ]
            # Compound movements first; exercises done recently pushed to the back for variety.
            candidates.sort(key=lambda ex: (ex["id"] in recent_exercise_ids, -self._activation_magnitude(ex)))

            picked_here: list[dict] = []
            for ex in candidates:
                if len(picked_here) >= per_pattern:
                    break
                vec = self._index.get_vector(ex["id"])
                if any(
                    cosine_similarity(vec, self._index.get_vector(c["id"])) > _NEAR_DUPLICATE_SIMILARITY
                    for c in picked_here
                ):
                    continue
                picked_here.append(ex)
            chosen.extend(picked_here)

        return chosen[:exercise_count] if exercise_count < len(chosen) else chosen

    def _volume_scheme(self, user: User) -> dict:
        base = dict(_VOLUME_BY_LEVEL.get(user.fitness_level, _VOLUME_BY_LEVEL["beginner"]))
        if "strength" in user.goals:
            return {"sets": base["sets"] + 1, "reps": "4-6", "rest": 120}
        if "endurance" in user.goals or "weight_loss" in user.goals:
            return {"sets": base["sets"], "reps": "12-15", "rest": 45}
        return base

    # ── Suggestibility filter + substitution/tooltip pass ───────────────

    def _cached_note(self, original_id: str, substitute_id: str) -> str | None:
        """Return an existing narration for this exact swap pair — from this
        generation's in-memory cache first, then any previously-persisted
        WorkoutExercise. Avoids re-calling the LLM for a swap we've already
        explained (common across the days of a week)."""
        key = (original_id, substitute_id)
        if key in self._note_cache:
            return self._note_cache[key]
        row = (
            self._db.query(WorkoutExercise)
            .filter(
                WorkoutExercise.substituted_for_id == original_id,
                WorkoutExercise.exercise_id == substitute_id,
                WorkoutExercise.substitution_note.isnot(None),
            )
            .first()
        )
        note = row.substitution_note if row else None
        if note:
            self._note_cache[key] = note
        return note

    def _pick_substitute(self, user_id: int, ex: dict, used_ids: set[str], picked_vectors: list):
        """Best safe substitute for `ex`: prefer one in the same movement
        pattern, skip anything already used in the day or near-identical
        (cosine > 0.93) to an exercise already in the plan."""
        subs = self._substitution.find_substitutes(user_id, ex["id"], top_k=8)
        same_pattern = [s for s in subs if s.exercise.get("movement_pattern") == ex.get("movement_pattern")]
        for cand in (same_pattern + [s for s in subs if s not in same_pattern]):
            if cand.exercise["id"] in used_ids:
                continue
            cvec = self._index.get_vector(cand.exercise["id"])
            if any(cosine_similarity(cvec, pv) > _NEAR_DUPLICATE_SIMILARITY for pv in picked_vectors):
                continue
            return cand
        return None

    async def _build_slots(self, user_id: int, generic: list[dict]) -> tuple[list[ExerciseSlot], list[str]]:
        sg_results = self._suggestibility.batch_compute(user_id, generic)

        ok_slots: list[tuple[int, ExerciseSlot]] = []
        blocked: list[tuple[int, dict, object]] = []
        warnings: list[str] = []
        used_ids: set[str] = set()
        picked_vectors: list = []

        for position, (ex, sg) in enumerate(zip(generic, sg_results)):
            if sg.state in (SuggestibilityState.SUPPRESSED, SuggestibilityState.COOLDOWN):
                blocked.append((position, ex, sg))
            else:
                ok_slots.append((position, ExerciseSlot(exercise=ex)))
                used_ids.add(ex["id"])
                picked_vectors.append(self._index.get_vector(ex["id"]))

        # Resolve substitutes sequentially (each pick constrains the next), then
        # narrate every swap that still needs it in ONE batched LLM call.
        swaps: list[tuple[int, dict, object, object]] = []
        for position, ex, sg in blocked:
            sub = self._pick_substitute(user_id, ex, used_ids, picked_vectors)
            if sub is None:
                warnings.append(f"No safe substitute found for {ex['name']} — dropped from the plan.")
                continue
            used_ids.add(sub.exercise["id"])
            picked_vectors.append(self._index.get_vector(sub.exercise["id"]))
            swaps.append((position, ex, sub, sg))

        notes_by_pos: dict[int, str] = {}
        to_narrate: list[tuple[int, dict, object, object]] = []
        for position, ex, sub, sg in swaps:
            cached = self._cached_note(ex["id"], sub.exercise["id"])
            if cached:
                notes_by_pos[position] = cached
            else:
                to_narrate.append((position, ex, sub, sg))

        if to_narrate:
            batch = [{"original": ex, "substitute": sub, "sg_result": sg} for _, ex, sub, sg in to_narrate]
            batch_notes = await explain_substitutions_batch(batch)
            for (position, ex, sub, _sg), note in zip(to_narrate, batch_notes):
                notes_by_pos[position] = note
                self._note_cache[(ex["id"], sub.exercise["id"])] = note

        for position, ex, sub, _sg in swaps:
            ok_slots.append((position, ExerciseSlot(
                exercise=sub.exercise, substituted_for=ex, substitution_note=notes_by_pos.get(position),
            )))

        ok_slots.sort(key=lambda pair: pair[0])
        return [slot for _, slot in ok_slots], warnings

    async def _build_day(self, user: User, target_date: date, day_index: int, workout_type: str) -> DayPlan:
        cfg = WORKOUT_TYPES[workout_type]
        recent_ids = self._recent_exercise_ids(user.id, target_date)
        exercise_count = self._exercise_count(user)
        generic = self._select_generic_exercises(user, cfg["patterns"], exercise_count, recent_ids)
        slots, warnings = await self._build_slots(user.id, generic)
        return DayPlan(
            day_index=day_index, date=target_date, is_rest=False,
            workout_type=workout_type, workout_label=cfg["label"],
            slots=slots, warnings=warnings,
        )

    # ── Public entry points ──────────────────────────────────────────────

    async def generate_day(self, user: User, target_date: date, day_index: int = 0) -> DayPlan:
        workout_type = self.resolve_day_type(user, target_date)
        if workout_type is None:
            return DayPlan(day_index=day_index, date=target_date, is_rest=True)
        return await self._build_day(user, target_date, day_index, workout_type)

    async def generate_week(self, user: User, start_date: date) -> list[DayPlan]:
        types = self._plan_week_types(user, start_date)
        days: list[DayPlan] = []
        for i, t in enumerate(types):
            d = start_date + timedelta(days=i)
            days.append(DayPlan(day_index=i, date=d, is_rest=True) if t is None else await self._build_day(user, d, i, t))
        return days

    # ── Persistence ──────────────────────────────────────────────────────

    def persist_day(self, user: User, day: DayPlan) -> WorkoutLog | None:
        if day.is_rest:
            return None
        volume = self._volume_scheme(user)
        started_at = datetime.combine(day.date, datetime.min.time(), tzinfo=timezone.utc)
        log = WorkoutLog(user_id=user.id, workout_type=day.workout_type, source="daily", started_at=started_at)
        for position, slot in enumerate(day.slots):
            log.exercises.append(WorkoutExercise(
                exercise_id=slot.exercise["id"],
                exercise_name=slot.exercise["name"],
                position=position,
                sets=volume["sets"],
                reps=volume["reps"],
                rest_seconds=volume["rest"],
                substituted_for_id=slot.substituted_for["id"] if slot.substituted_for else None,
                substituted_for_name=slot.substituted_for["name"] if slot.substituted_for else None,
                substitution_note=slot.substitution_note,
            ))
        self._db.add(log)
        self._db.commit()
        self._db.refresh(log)
        return log
