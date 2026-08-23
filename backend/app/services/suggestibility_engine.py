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
    "shoulder": {"high_shoulder_flexion_under_load", "shoulder_impingement_risk", "rotator_cuff_load"},
    "rotator": {"high_shoulder_flexion_under_load", "shoulder_impingement_risk", "rotator_cuff_load"},
    "elbow": {"elbow_flexion_load", "wrist_extension_load"},
    "wrist": {"wrist_extension_load"},
    "knee": {"high_knee_flexion_load", "valgus_knee_stress", "patellar_tendon_load"},
    "patellar": {"patellar_tendon_load", "high_knee_flexion_load"},
    "lower back": {"lumbar_compression", "lumbar_shear", "spinal_flexion_under_load"},
    "lumbar": {"lumbar_compression", "lumbar_shear", "spinal_flexion_under_load"},
    "spine": {"lumbar_compression", "lumbar_shear", "spinal_flexion_under_load"},
    "hip": {"hip_flexion_load"},
    "neck": {"cervical_load"},
    "cervical": {"cervical_load"},
    "ankle": {"ankle_dorsiflexion_load"},
    "achilles": {"ankle_dorsiflexion_load"},
    "hamstring": {"hamstring_peak_tension"},
    "groin": {"hip_adductor_load"},
    "adductor": {"hip_adductor_load"},
}


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
            force_conflict = exercise_force in restricted
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

