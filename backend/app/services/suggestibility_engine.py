from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session
from app.models.rejection import RejectionEvent
from app.models.user import Injury

_COOLDOWN_DAYS = {"too_sore": 3, "too_tired": 2, "not_today": 1}
_PREFERENCE_DELTA = {
    "dont_like":   -0.15,
    "too_easy":    -0.10,
    "too_hard":    -0.10,
    "bad_form":    -0.08,
    "too_long":    -0.05,
    "no_equipment": -0.05,
}
_MIN_PREFERENCE_SCORE = 0.10

_BODY_PART_FLAGS = {
    # Keys must match the actual joint_stress_flags vocabulary in exercises.json
    # (verified against the dataset — see Stage 7 notes on the previous
    # mismatched version of this table, which silently matched nothing for
    # knee/elbow/wrist/hip/neck/ankle injuries).
    "shoulder": {"high_shoulder_flexion_under_load", "rotator_cuff_under_load", "shoulder_abduction_under_load"},
    "rotator": {"high_shoulder_flexion_under_load", "rotator_cuff_under_load", "shoulder_abduction_under_load"},
    "elbow": {"elbow_flexion_under_load", "elbow_extension_under_load"},
    "wrist": {"wrist_extension_under_load", "wrist_flexion_under_load"},
    "knee": {"knee_extension_under_load", "knee_flexion_under_load", "knee_valgus_risk"},
    "patellar": {"knee_extension_under_load", "knee_valgus_risk"},
    "lower back": {"lumbar_compression", "lumbar_shear", "lumbar_rotation_load"},
    "lumbar": {"lumbar_compression", "lumbar_shear", "lumbar_rotation_load"},
    "spine": {"lumbar_compression", "lumbar_shear", "lumbar_rotation_load"},
    "hip": {"hip_flexion_under_load"},
    "neck": {"cervical_spine_load"},
    "cervical": {"cervical_spine_load"},
    "ankle": {"ankle_plantar_flexion_load"},
    "achilles": {"ankle_plantar_flexion_load"},
    # No dedicated hamstring/groin/adductor flags exist in the current dataset;
    # hamstring strain is approximated via the hip/knee flexion flags it's
    # clinically tied to during hinge movements.
    "hamstring": {"hip_flexion_under_load", "knee_flexion_under_load"},
}

# Muscles that belong to an injured region. Used to scope a force-direction
# restriction (e.g. against_gravity) to exercises that actually load the injured
# area — so a right-shoulder injury blocks the overhead press but not the calf
# raise, even though both are "against gravity".
_BODY_PART_MUSCLES = {
    "shoulder":  {"anterior_deltoid", "lateral_deltoid", "posterior_deltoid", "traps_upper"},
    "rotator":   {"anterior_deltoid", "lateral_deltoid", "posterior_deltoid"},
    "deltoid":   {"anterior_deltoid", "lateral_deltoid", "posterior_deltoid"},
    "elbow":     {"biceps", "triceps", "forearms"},
    "bicep":     {"biceps", "forearms"},
    "tricep":    {"triceps"},
    "wrist":     {"forearms"},
    "forearm":   {"forearms"},
    "knee":      {"quads", "hamstrings"},
    "patellar":  {"quads"},
    "quad":      {"quads"},
    "lower back": {"erector_spinae", "lats", "glutes"},
    "lumbar":    {"erector_spinae", "lats", "glutes"},
    "spine":     {"erector_spinae"},
    "back":      {"lats", "rhomboids", "traps_mid", "traps_upper", "erector_spinae"},
    "hip":       {"glutes", "hip_flexors", "adductors", "abductors"},
    "glute":     {"glutes"},
    "groin":     {"adductors"},
    "adductor":  {"adductors"},
    "neck":      {"traps_upper"},
    "cervical":  {"traps_upper"},
    "ankle":     {"calves"},
    "achilles":  {"calves"},
    "calf":      {"calves"},
    "hamstring": {"hamstrings"},
}
_REGION_ACTIVATION_THRESHOLD = 0.4


class SuggestibilityState(str, Enum):
    ELIGIBLE = "eligible"
    PREFERENCE_PENALIZED = "preference_penalized"
    COOLDOWN = "cooldown"
    SUPPRESSED = "suppressed"


@dataclass
class SuggestibilityResult:
    exercise_id: str
    state: SuggestibilityState = SuggestibilityState.ELIGIBLE
    preference_score: float = 1.0
    suppressed_until: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    suppression_reason: Optional[str] = None
    blocked_flags: set = field(default_factory=set)


def flags_for_body_part(body_part: str) -> set:
    bp = body_part.lower()
    result: set = set()
    for keyword, flags in _BODY_PART_FLAGS.items():
        if keyword in bp:
            result |= flags
    return result


def muscles_for_body_part(body_part: str) -> set:
    bp = body_part.lower()
    result: set = set()
    for keyword, muscles in _BODY_PART_MUSCLES.items():
        if keyword in bp:
            result |= muscles
    return result


def _exercise_loads_region(exercise: dict, region_muscles: set) -> bool:
    """True if the exercise meaningfully loads any muscle of the injured region."""
    if not region_muscles:
        return True  # unknown region — fall back to the old blunt behaviour
    activation = exercise.get("muscle_activation", {})
    return any(activation.get(m, 0.0) >= _REGION_ACTIVATION_THRESHOLD for m in region_muscles)


def compute_preference_score(rejections: list) -> float:
    score = 1.0
    for r in rejections:
        score += _PREFERENCE_DELTA.get(r.reason, 0.0)
    return max(_MIN_PREFERENCE_SCORE, round(score, 3))


class SuggestibilityEngine:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._injuries_cache: dict = {}
        self._rejections_cache: dict = {}

    def compute(self, user_id: int, exercise: dict, now: Optional[datetime] = None) -> SuggestibilityResult:
        if now is None:
            now = datetime.now(timezone.utc)
        injury_result = self._check_injuries(user_id, exercise, now)
        if injury_result is not None:
            return injury_result
        rejections = self._load_rejections(user_id, exercise["id"])
        cooldown_result = self._check_cooldown(exercise["id"], rejections, now)
        if cooldown_result is not None:
            return cooldown_result
        pref = [r for r in rejections if r.reason in _PREFERENCE_DELTA]
        score = compute_preference_score(pref)
        state = SuggestibilityState.PREFERENCE_PENALIZED if score < 1.0 else SuggestibilityState.ELIGIBLE
        return SuggestibilityResult(exercise_id=exercise["id"], state=state, preference_score=score)

    def batch_compute(self, user_id: int, exercises: list, now: Optional[datetime] = None) -> list:
        if now is None:
            now = datetime.now(timezone.utc)
        return [self.compute(user_id, ex, now) for ex in exercises]

    def _load_injuries(self, user_id: int) -> list:
        if user_id not in self._injuries_cache:
            self._injuries_cache[user_id] = (
                self._db.query(Injury)
                .filter(Injury.user_id == user_id, Injury.is_active == True)
                .all()
            )
        return self._injuries_cache[user_id]

    def _load_rejections(self, user_id: int, exercise_id: str) -> list:
        key = (user_id, exercise_id)
        if key not in self._rejections_cache:
            self._rejections_cache[key] = (
                self._db.query(RejectionEvent)
                .filter(RejectionEvent.user_id == user_id, RejectionEvent.exercise_id == exercise_id)
                .order_by(RejectionEvent.created_at.desc())
                .all()
            )
        return self._rejections_cache[key]

    def _check_injuries(self, user_id: int, exercise: dict, now: datetime) -> Optional[SuggestibilityResult]:
        exercise_flags = set(exercise.get("joint_stress_flags", []))
        exercise_force = exercise.get("force_direction", "")
        for injury in self._load_injuries(user_id):
            if injury.healed_at is not None:
                continue
            implied = flags_for_body_part(injury.body_part)
            restricted: set = set()
            if getattr(injury, "restricted_force_directions_json", None):
                restricted = set(json.loads(injury.restricted_force_directions_json))
            conflicting = exercise_flags & implied
            force_restricted = exercise_force in restricted

            # A force-direction restriction only bites when the exercise also
            # loads the injured region — otherwise a blanket "against_gravity"
            # restriction blocks half the dataset (calf raises, planks, squats
            # for a shoulder injury). A joint-flag match always counts as
            # loading the region.
            region_muscles = muscles_for_body_part(injury.body_part)
            loads_region = bool(conflicting) or _exercise_loads_region(exercise, region_muscles)
            force_conflict = force_restricted and loads_region

            # When the injury explicitly restricts certain force directions
            # (the physio said "avoid against-gravity loading"), an exercise
            # that uses a *permitted* direction isn't a hard block even if it
            # trips a joint-stress flag — supported bench press vs. push-up for
            # a shoulder. The flag becomes informational, not suppressing.
            if conflicting and restricted and not force_restricted:
                conflicting = set()

            if not conflicting and not force_conflict:
                continue
            suppressed_until = None
            if injury.recovery_expectation_days is not None:
                created = injury.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                suppressed_until = created + timedelta(days=injury.recovery_expectation_days)
            parts = []
            if conflicting:
                parts.append(f"joint stress: {', '.join(sorted(conflicting))}")
            if force_conflict:
                parts.append(f"force direction '{exercise_force}' restricted")
            return SuggestibilityResult(
                exercise_id=exercise["id"],
                state=SuggestibilityState.SUPPRESSED,
                suppressed_until=suppressed_until,
                suppression_reason=f"{injury.body_part} injury — {'; '.join(parts)}",
                blocked_flags=conflicting,
            )
        return None

    def _check_cooldown(self, exercise_id: str, rejections: list, now: datetime) -> Optional[SuggestibilityResult]:
        for r in rejections:
            days = _COOLDOWN_DAYS.get(r.reason)
            if days is None:
                continue
            created = r.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            cooldown_until = created + timedelta(days=days)
            if cooldown_until > now:
                return SuggestibilityResult(
                    exercise_id=exercise_id,
                    state=SuggestibilityState.COOLDOWN,
                    cooldown_until=cooldown_until,
                    suppression_reason=f"Cooldown until {cooldown_until.date()} ({r.reason})",
                )
        return None

