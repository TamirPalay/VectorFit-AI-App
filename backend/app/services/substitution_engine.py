from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.ml.embeddings import ExerciseIndex
from app.services.suggestibility_engine import SuggestibilityEngine, SuggestibilityState


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
        candidate_pool: int = 20,
    ) -> list[Substitute]:
        """
        Return up to top_k eligible substitutes for exercise_id, ranked by
        similarity × preference_score.

        candidate_pool: how many FAISS neighbours to evaluate before filtering.
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
