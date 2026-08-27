"""
Shared exercise search / filter / facet logic — Stage 8 (custom builder).

Used by both the user-agnostic browse endpoint (GET /exercises) and the
workout-scoped picker (GET /users/{id}/workouts/{wid}/suggestions) so the two
can't drift. Everything here is deterministic Python over the in-memory
ExerciseIndex — no LLM, no DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.data.muscles import (
    BODY_PART_MATCH_THRESHOLD,
    BODY_PARTS,
    muscles_for_body_part,
)

_COMPOUND_MIN_STRONG_MUSCLES = 3
_STRONG_ACTIVATION = 0.5
# An exact-muscle filter is looser than a body-part chip — "involves this muscle
# meaningfully" rather than "trains this area".
MUSCLE_MATCH_THRESHOLD = 0.3


def is_compound(ex: dict) -> bool:
    """Compound = at least 3 muscles worked at >= 0.5 activation."""
    strong = sum(1 for v in ex.get("muscle_activation", {}).values() if v >= _STRONG_ACTIVATION)
    return strong >= _COMPOUND_MIN_STRONG_MUSCLES


def mechanic_of(ex: dict) -> str:
    return "compound" if is_compound(ex) else "isolation"


def body_parts_of(ex: dict) -> list[str]:
    """Fine-grained body-part chips (no umbrellas) an exercise trains at or
    above the match threshold."""
    activation = ex.get("muscle_activation", {})
    hit = []
    for part, muscles in BODY_PARTS.items():
        if any(activation.get(m, 0.0) >= BODY_PART_MATCH_THRESHOLD for m in muscles):
            hit.append(part)
    return hit


@dataclass
class ExerciseQuery:
    q: str | None = None
    body_parts: list[str] = field(default_factory=list)          # OR-combined
    muscles: list[str] = field(default_factory=list)             # OR-combined, activation >= 0.3
    equipment: list[str] = field(default_factory=list)
    equipment_match: str = "uses_any"                            # "uses_any" | "doable_with"
    movement_patterns: list[str] = field(default_factory=list)   # OR-combined
    force_directions: list[str] = field(default_factory=list)    # OR-combined
    mechanic: str | None = None                                  # "compound" | "isolation"
    exclude_ids: set[str] = field(default_factory=set)
    sort: str = "relevance"                                      # relevance|name|compound_first

    def normalized(self) -> "ExerciseQuery":
        return ExerciseQuery(
            q=(self.q or "").strip().lower() or None,
            body_parts=[b.strip().lower() for b in self.body_parts if b.strip()],
            muscles=[m.strip() for m in self.muscles if m.strip()],
            equipment=[e.strip() for e in self.equipment if e.strip()],
            equipment_match=self.equipment_match,
            movement_patterns=[p.strip().lower() for p in self.movement_patterns if p.strip()],
            force_directions=[f.strip().lower() for f in self.force_directions if f.strip()],
            mechanic=(self.mechanic.strip().lower() if self.mechanic else None),
            exclude_ids=set(self.exclude_ids),
            sort=self.sort or "relevance",
        )


def _matches_text(ex: dict, q: str) -> bool:
    return q in ex["name"].lower() or q in ex.get("description", "").lower()


def _matches_body_parts(ex: dict, parts: list[str]) -> bool:
    activation = ex.get("muscle_activation", {})
    for part in parts:
        muscles = muscles_for_body_part(part)
        if muscles and any(activation.get(m, 0.0) >= BODY_PART_MATCH_THRESHOLD for m in muscles):
            return True
    return False


def _matches_muscles(ex: dict, muscles: list[str]) -> bool:
    activation = ex.get("muscle_activation", {})
    return any(activation.get(m, 0.0) >= MUSCLE_MATCH_THRESHOLD for m in muscles)


def _target_muscles(query: "ExerciseQuery") -> set[str]:
    """Union of the muscles implied by the query's body-part + muscle filters —
    used to rank 'relevance' when there's no text query."""
    out: set[str] = set(query.muscles)
    for part in query.body_parts:
        out |= muscles_for_body_part(part)
    return out


def _target_score(ex: dict, muscles: set[str]) -> float:
    activation = ex.get("muscle_activation", {})
    return max((activation.get(m, 0.0) for m in muscles), default=0.0)


def _matches_equipment(ex: dict, equipment: list[str], mode: str) -> bool:
    required = set(ex.get("equipment_required", []))
    chosen = set(equipment)
    if mode == "doable_with":
        return required <= (chosen | {"bodyweight"})
    return bool(required & chosen)  # "uses_any"


def _text_rank(ex: dict, q: str) -> int:
    name = ex["name"].lower()
    if name.startswith(q):
        return 0
    if q in name:
        return 1
    return 2  # description-only match


def apply_filters(exercises: list[dict], query: ExerciseQuery) -> list[dict]:
    """Filter then sort. Does not mutate the input list or its dicts."""
    query = query.normalized()
    out = []
    for ex in exercises:
        if ex["id"] in query.exclude_ids:
            continue
        if query.q and not _matches_text(ex, query.q):
            continue
        if query.body_parts and not _matches_body_parts(ex, query.body_parts):
            continue
        if query.muscles and not _matches_muscles(ex, query.muscles):
            continue
        if query.equipment and not _matches_equipment(ex, query.equipment, query.equipment_match):
            continue
        if query.movement_patterns and ex.get("movement_pattern") not in query.movement_patterns:
            continue
        if query.force_directions and ex.get("force_direction") not in query.force_directions:
            continue
        if query.mechanic and mechanic_of(ex) != query.mechanic:
            continue
        out.append(ex)

    if query.sort == "name":
        out.sort(key=lambda e: e["name"].lower())
    elif query.sort == "compound_first":
        out.sort(key=lambda e: (not is_compound(e), e["name"].lower()))
    else:  # "relevance"
        if query.q:
            out.sort(key=lambda e: (_text_rank(e, query.q), e["name"].lower()))
        else:
            targets = _target_muscles(query)
            if targets:
                out.sort(key=lambda e: (-_target_score(e, targets), not is_compound(e), e["name"].lower()))
            else:
                out.sort(key=lambda e: (not is_compound(e), e["name"].lower()))
    return out


def compute_facets(exercises: list[dict]) -> dict[str, dict[str, int]]:
    """Counts per filterable dimension over the given set (typically the set
    filtered by the text query only, so chip counts stay stable as the user
    toggles the other chips)."""
    facets: dict[str, dict[str, int]] = {
        "body_part": {},
        "equipment": {},
        "movement_pattern": {},
        "force_direction": {},
        "mechanic": {"compound": 0, "isolation": 0},
    }
    for ex in exercises:
        for part in body_parts_of(ex):
            facets["body_part"][part] = facets["body_part"].get(part, 0) + 1
        for eq in ex.get("equipment_required", []):
            facets["equipment"][eq] = facets["equipment"].get(eq, 0) + 1
        mp = ex.get("movement_pattern")
        if mp:
            facets["movement_pattern"][mp] = facets["movement_pattern"].get(mp, 0) + 1
        fd = ex.get("force_direction")
        if fd:
            facets["force_direction"][fd] = facets["force_direction"].get(fd, 0) + 1
        facets["mechanic"][mechanic_of(ex)] += 1

    for key, counts in facets.items():
        facets[key] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return facets
