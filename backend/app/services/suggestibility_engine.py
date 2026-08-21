from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session
from app.models.rejection import RejectionEvent
from app.models.user import Injury

_COOLDOWN_DAYS = {"too_sore": 3, "too_tired": 2}
_PREFERENCE_DELTA = {"dont_like": -0.15, "too_easy": -0.10, "too_hard": -0.10, "no_equipment": -0.05}
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

