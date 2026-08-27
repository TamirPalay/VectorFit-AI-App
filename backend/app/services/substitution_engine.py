from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.data.muscles import MUSCLES
from app.ml.embeddings import ExerciseIndex
from app.services.suggestibility_engine import SuggestibilityEngine, SuggestibilityState

COMPLEMENT_COVERAGE_THRESHOLD = 0.85  # suggest complements when coverage is below this


@dataclass
class Substitute:
    exercise: dict
    similarity: float        # cosine similarity to the original (0–1)
    coverage: float          # fraction of original's muscle activation covered
    preference_score: float  # from suggestibility engine (1.0 = fully preferred)
    rank_score: float        # combined score used for ordering


class SubstitutionEngine:
    """
    Given a suppressed exercise, find the best safe alternatives for a user.

    Ranking: rank_score = similarity × preference_score
    Coverage tells you how biomechanically equivalent the swap is.
    """

    def __init__(self, db: Session, index: ExerciseIndex) -> None:
        self._db = db
        self._index = index
        self._suggestibility = SuggestibilityEngine(db)

    def find_substitutes(
        self,
        user_id: int,
        exercise_id: str,
        top_k: int = 5,
        candidate_pool: int = 60,
    ) -> list[Substitute]:
        """
        Return up to top_k eligible substitutes for exercise_id, ranked by
        similarity × preference_score.

        candidate_pool: how many FAISS neighbours to evaluate before filtering.
        60 (not 20) because a user with a blanket force_direction restriction
        (e.g. against_gravity) can block most of an exercise's nearest
        neighbours outright — a narrow pool then finds nothing even when a
        perfectly good supported alternative exists further down the ranking.
        The dataset is small (~300 exercises) so a wider pool costs nothing.
        Raise ValueError if exercise_id is not in the index.
        """
        all_exercises = {ex["id"]: ex for ex in self._index.exercises}
        if exercise_id not in all_exercises:
            raise ValueError(f"Exercise '{exercise_id}' not found in index")

        # Get the joint_stress_flags of the original so FAISS can pre-filter
        # exercises that share the same blocked flags (saves suggestibility calls).
        original = all_exercises[exercise_id]

        # Fetch nearest neighbours (excluding the original itself)
        neighbours = self._index.find_similar(
            exercise_id=exercise_id,
            top_k=candidate_pool,
            exclude_ids={exercise_id},
        )

        substitutes: list[Substitute] = []
        candidate_exercises = [n["exercise"] for n in neighbours]

        # Run all candidates through suggestibility in one batch
        results = self._suggestibility.batch_compute(user_id, candidate_exercises)
        result_map = {r.exercise_id: r for r in results}

        for neighbour in neighbours:
            ex = neighbour["exercise"]
            ex_id = ex["id"]
            if ex_id not in result_map:
                continue
            sg = result_map[ex_id]

            # Only offer ELIGIBLE or PREFERENCE_PENALIZED exercises as substitutes
            if sg.state in (SuggestibilityState.SUPPRESSED, SuggestibilityState.COOLDOWN):
                continue

            similarity = neighbour["similarity"]
            coverage = self._index.compute_coverage(
                target_id=exercise_id,
                candidate_ids=[ex_id],
            )
            rank_score = round(similarity * sg.preference_score, 4)

            substitutes.append(Substitute(
                exercise=ex,
                similarity=round(similarity, 4),
                coverage=round(coverage, 4),
                preference_score=sg.preference_score,
                rank_score=rank_score,
            ))

            if len(substitutes) >= top_k:
                break

        substitutes.sort(key=lambda s: s.rank_score, reverse=True)
        return substitutes

    def find_complements(
        self,
        user_id: int,
        target_id: str,
        substitute_id: str,
        top_k: int = 4,
    ) -> list[dict]:
        """
        Find exercises that fill the activation gap left by a primary substitute.

        Computes the residual vector (what the substitute leaves uncovered),
        queries FAISS for exercises targeting those muscles, filters through
        suggestibility, and returns the top_k ranked by combined coverage
        (substitute + complement together).

        Returns a list of dicts: {exercise, combined_coverage, preference_score}
        """
        target_ex = self._index.get_by_id(target_id)
        sub_ex = self._index.get_by_id(substitute_id)
        if not target_ex or not sub_ex:
            return []

        target_raw = np.array(
            [target_ex["muscle_activation"].get(m, 0.0) for m in MUSCLES],
            dtype=np.float32,
        )
        sub_raw = np.array(
            [sub_ex["muscle_activation"].get(m, 0.0) for m in MUSCLES],
            dtype=np.float32,
        )
        residual = np.maximum(0.0, target_raw - sub_raw)

        if np.linalg.norm(residual) < 1e-6:
            return []

        candidates = self._index.find_similar_to_vector(
            query_vec=residual,
            top_k=top_k + 10,
            exclude_ids={target_id, substitute_id},
        )

        candidate_exercises = [n["exercise"] for n in candidates]
        sg_results = self._suggestibility.batch_compute(user_id, candidate_exercises)
        result_map = {r.exercise_id: r for r in sg_results}

        complements: list[dict] = []
        for n in candidates:
            ex = n["exercise"]
            ex_id = ex["id"]
            sg = result_map.get(ex_id)
            if sg is None:
                continue
            if sg.state in (SuggestibilityState.SUPPRESSED, SuggestibilityState.COOLDOWN):
                continue

            combined_coverage = self._index.compute_coverage(
                target_id=target_id,
                candidate_ids=[substitute_id, ex_id],
            )
            complements.append({
                "exercise": ex,
                "combined_coverage": round(combined_coverage, 4),
                "preference_score": sg.preference_score,
            })
            if len(complements) >= top_k:
                break

        complements.sort(key=lambda c: c["combined_coverage"], reverse=True)
        return complements

    def find_substitutes_for_set(
        self,
        user_id: int,
        exercise_ids: list[str],
        top_k_each: int = 3,
    ) -> dict[str, list[Substitute]]:
        """Find substitutes for multiple exercises at once."""
        return {
            ex_id: self.find_substitutes(user_id, ex_id, top_k=top_k_each)
            for ex_id in exercise_ids
        }
