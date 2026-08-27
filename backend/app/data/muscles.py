"""
Canonical muscle list for VectorFit.

Every exercise's muscle_activation dict must contain ALL 22 keys below,
with a float value in [0.0, 1.0]. This ensures every vector has the same
dimensionality, which is required for FAISS cosine similarity search.

Scale:
  0.9 – 1.0  primary mover
  0.6 – 0.8  strong secondary / major stabilizer
  0.3 – 0.5  moderate stabilizer
  0.1 – 0.2  minor activation / postural stabilizer
  0.0         not meaningfully recruited
"""

MUSCLES: list[str] = [
    "chest",
    "anterior_deltoid",
    "lateral_deltoid",
    "posterior_deltoid",
    "triceps",
    "biceps",
    "forearms",
    "lats",
    "rhomboids",
    "traps_upper",
    "traps_mid",
    "serratus_anterior",
    "abs",
    "obliques",
    "erector_spinae",
    "hip_flexors",
    "quads",
    "hamstrings",
    "glutes",
    "adductors",
    "abductors",
    "calves",
]

MUSCLE_SET: set[str] = set(MUSCLES)
MUSCLE_INDEX: dict[str, int] = {m: i for i, m in enumerate(MUSCLES)}

# ── Muscle display groups (for the front/back body SVG map) ───────────────────
# Maps muscle id → {"display_name", "side"} where side is "front" or "back"
MUSCLE_DISPLAY: dict[str, dict] = {
    "chest":             {"display_name": "Chest",              "side": "front"},
    "anterior_deltoid":  {"display_name": "Front Shoulder",     "side": "front"},
    "lateral_deltoid":   {"display_name": "Side Shoulder",      "side": "front"},
    "posterior_deltoid": {"display_name": "Rear Shoulder",      "side": "back"},
    "triceps":           {"display_name": "Triceps",            "side": "back"},
    "biceps":            {"display_name": "Biceps",             "side": "front"},
    "forearms":          {"display_name": "Forearms",           "side": "front"},
    "lats":              {"display_name": "Lats",               "side": "back"},
    "rhomboids":         {"display_name": "Rhomboids",          "side": "back"},
    "traps_upper":       {"display_name": "Upper Traps",        "side": "back"},
    "traps_mid":         {"display_name": "Mid Traps",          "side": "back"},
    "serratus_anterior": {"display_name": "Serratus",           "side": "front"},
    "abs":               {"display_name": "Abs",                "side": "front"},
    "obliques":          {"display_name": "Obliques",           "side": "front"},
    "erector_spinae":    {"display_name": "Lower Back",         "side": "back"},
    "hip_flexors":       {"display_name": "Hip Flexors",        "side": "front"},
    "quads":             {"display_name": "Quads",              "side": "front"},
    "hamstrings":        {"display_name": "Hamstrings",         "side": "back"},
    "glutes":            {"display_name": "Glutes",             "side": "back"},
    "adductors":         {"display_name": "Inner Thighs",       "side": "front"},
    "abductors":         {"display_name": "Outer Hips",         "side": "back"},
    "calves":            {"display_name": "Calves",             "side": "back"},
}

# ── Body-part groups (for the custom-builder quick filters) ───────────────────
# Maps a coarse "body part" chip to the fine-grained muscles it covers. An
# exercise matches a body part if ANY of these muscles is activated at or above
# BODY_PART_MATCH_THRESHOLD. The bar is deliberately high (0.5 = "strong secondary"
# or above) so a chip means "this exercise trains that area", not "uses it as a
# stabilizer". Umbrella groups (arms, legs) expand to the union of their sub-groups.
BODY_PART_MATCH_THRESHOLD = 0.5

BODY_PARTS: dict[str, set[str]] = {
    "chest":       {"chest", "serratus_anterior"},
    "back":        {"lats", "rhomboids", "traps_upper", "traps_mid", "erector_spinae"},
    "lower_back":  {"erector_spinae"},
    "shoulders":   {"anterior_deltoid", "lateral_deltoid", "posterior_deltoid"},
    "biceps":      {"biceps"},
    "triceps":     {"triceps"},
    "forearms":    {"forearms"},
    "core":        {"abs", "obliques"},
    "quads":       {"quads"},
    "hamstrings":  {"hamstrings"},
    "glutes":      {"glutes"},
    "hip_flexors": {"hip_flexors"},
    "adductors":   {"adductors"},
    "abductors":   {"abductors"},
    "calves":      {"calves"},
}

_BODY_PART_UMBRELLAS: dict[str, tuple[str, ...]] = {
    "arms": ("biceps", "triceps", "forearms"),
    "legs": ("quads", "hamstrings", "glutes", "calves", "adductors", "abductors", "hip_flexors"),
}

BODY_PART_NAMES: list[str] = list(BODY_PARTS) + list(_BODY_PART_UMBRELLAS)


def muscles_for_body_part(name: str) -> set[str]:
    """Resolve a body-part chip (incl. umbrellas) to its set of muscle ids.
    Unknown names return an empty set."""
    key = name.strip().lower()
    if key in _BODY_PART_UMBRELLAS:
        out: set[str] = set()
        for sub in _BODY_PART_UMBRELLAS[key]:
            out |= BODY_PARTS.get(sub, set())
        return out
    return set(BODY_PARTS.get(key, set()))


# ── Joint-stress flag vocabulary ──────────────────────────────────────────────
# Used to filter exercises against a user's active injury restrictions.
# An exercise's joint_stress_flags list contains zero or more of these strings.
JOINT_STRESS_FLAGS: set[str] = {
    "high_shoulder_flexion_under_load",   # push-up, OHP, dips, incline press
    "shoulder_abduction_under_load",      # lateral raises, OHP, pull-ups
    "rotator_cuff_under_load",            # face pull, upright row, lateral raise
    "elbow_extension_under_load",         # skull crusher, tricep pushdown, dips
    "elbow_flexion_under_load",           # curls, rows, pull-ups
    "wrist_extension_under_load",         # push-ups, front squat rack, planks
    "wrist_flexion_under_load",           # barbell curls
    "lumbar_compression",                 # squats, OHP, deadlift
    "lumbar_shear",                       # bent-over row, RDL, good morning
    "lumbar_rotation_load",               # Russian twist, oblique work
    "cervical_spine_load",                # shrugs, back squat, crunch (hands behind head)
    "knee_flexion_under_load",            # squats, leg press, lunges, leg curl
    "knee_extension_under_load",          # leg extension machine
    "knee_valgus_risk",                   # lunges, single-leg movements
    "hip_flexion_under_load",             # hanging leg raise, leg press deep
    "ankle_plantar_flexion_load",         # calf raises
}

# ── Movement pattern vocabulary ───────────────────────────────────────────────
MOVEMENT_PATTERNS: set[str] = {
    "push",    # chest/shoulder/triceps pushing away
    "pull",    # back/biceps pulling toward body
    "hinge",   # hip hinge — deadlift pattern
    "squat",   # knee-dominant lower body
    "carry",   # loaded carries (farmer's walk, etc.)
    "core",    # core-dominant (plank, crunch, etc.)
}

# ── Force direction vocabulary ────────────────────────────────────────────────
FORCE_DIRECTIONS: set[str] = {
    "against_gravity",  # bodyweight or free overhead — joints bear gravity load
    "supported",        # body supported by bench/seat — joints bear external load only
    "horizontal",       # primary force is horizontal (rows, cable flies)
    "vertical",         # primary force is vertical (overhead press, pulldowns)
}
