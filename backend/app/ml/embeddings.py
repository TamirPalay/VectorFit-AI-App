"""
backend/app/ml/embeddings.py
-----------------------------
FAISS index over exercise muscle-activation vectors.

Concept
-------
Each exercise has a 22-dimensional muscle activation vector — one float per
muscle (0.0 = not used, 1.0 = primary mover). We normalise these to unit
length, then build a FAISS IndexFlatIP (inner-product) index. Because both
query and stored vectors are unit-normalised, inner product == cosine
similarity. So "nearest neighbours" = "exercises that activate the same
muscles in similar proportions."

This gives us sub-millisecond similarity search across the full exercise
dataset — no LLM call needed at substitution time.

Usage
-----
    from app.ml.embeddings import ExerciseIndex

    index = ExerciseIndex.load()          # loads from exercises.json
    results = index.find_similar("push_up", top_k=5)
    # → [{"exercise": {...}, "similarity": 0.97}, ...]

    # With a restriction mask (blocked joint-stress flags):
    results = index.find_similar(
        "push_up",
        top_k=5,
        blocked_flags={"high_shoulder_flexion_under_load"},
    )
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.data.muscles import MUSCLES, MUSCLE_INDEX

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    # Fallback: pure-numpy cosine similarity (slower but no install needed for tests)

EXERCISES_JSON = Path(__file__).parent.parent / "data" / "exercises.json"


def activation_to_vector(muscle_activation: dict[str, float]) -> np.ndarray:
    """
    Convert a muscle_activation dict to a normalised numpy float32 vector.

    The vector order follows MUSCLES (muscles.py). Missing muscles default to 0.
    Normalisation to unit length enables cosine similarity via inner product.
    """
    vec = np.zeros(len(MUSCLES), dtype=np.float32)
    for muscle, value in muscle_activation.items():
        if muscle in MUSCLE_INDEX:
            vec[MUSCLE_INDEX[muscle]] = float(value)

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two already-normalised vectors."""
    return float(np.dot(a, b))


class ExerciseIndex:
    """
    In-memory FAISS (or numpy fallback) index over all exercises.

    Load once at startup (inside FastAPI's startup event), then reuse
    across requests. Thread-safe for reads.
    """

    def __init__(self, exercises: list[dict], vectors: np.ndarray):
        self._exercises = exercises          # original dicts, same order as vectors
        self._vectors = vectors              # shape (n_exercises, 22), unit-normalised
        self._id_to_idx: dict[str, int] = {
            ex["id"]: i for i, ex in enumerate(exercises)
        }

        if FAISS_AVAILABLE:
            dim = vectors.shape[1]
            self._index = faiss.IndexFlatIP(dim)  # inner product on unit vecs = cosine sim
            self._index.add(vectors)
        else:
            self._index = None  # will use numpy fallback

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path = EXERCISES_JSON) -> "ExerciseIndex":
        """Load exercises.json and build the index."""
        with open(path) as f:
            dataset = json.load(f)

        exercises = dataset["exercises"]
        vectors = np.stack(
            [activation_to_vector(ex["muscle_activation"]) for ex in exercises]
        ).astype(np.float32)

        return cls(exercises, vectors)

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_by_id(self, exercise_id: str) -> dict | None:
        idx = self._id_to_idx.get(exercise_id)
        if idx is None:
            return None
        return self._exercises[idx]

    def get_vector(self, exercise_id: str) -> np.ndarray | None:
        idx = self._id_to_idx.get(exercise_id)
        if idx is None:
            return None
        return self._vectors[idx]

    def find_similar(
        self,
        exercise_id: str,
        top_k: int = 10,
        blocked_flags: set[str] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[dict]:
        """
        Find the top-k most similar exercises to the given exercise_id.

        Args:
            exercise_id: The exercise to find substitutes for.
            top_k: How many results to return (after filtering).
            blocked_flags: Joint-stress flags that candidates must NOT have.
                           Typically the union of the user's active injury restrictions.
            exclude_ids: Exercise IDs to always exclude (e.g. the original exercise).

        Returns:
            List of dicts ordered by similarity (highest first):
            [{"exercise": {...}, "similarity": 0.97}, ...]
        """
        blocked_flags = blocked_flags or set()
        exclude_ids = (exclude_ids or set()) | {exercise_id}

        query_vec = self.get_vector(exercise_id)
        if query_vec is None:
            return []

        query_vec = query_vec.reshape(1, -1)

        if FAISS_AVAILABLE and self._index is not None:
            # Fetch more candidates than needed because we'll filter some out
            fetch_k = min(len(self._exercises), top_k * 4 + 20)
            similarities, indices = self._index.search(query_vec, fetch_k)
            candidates = [
                (int(idx), float(sim))
                for idx, sim in zip(indices[0], similarities[0])
                if idx >= 0
            ]
        else:
            # Numpy fallback: compute all cosine similarities
            sims = (self._vectors @ query_vec.T).flatten()
            order = np.argsort(sims)[::-1]
            candidates = [(int(i), float(sims[i])) for i in order]

        results = []
        for idx, similarity in candidates:
            ex = self._exercises[idx]
            if ex["id"] in exclude_ids:
                continue
            if blocked_flags & set(ex.get("joint_stress_flags", [])):
                continue
            results.append({"exercise": ex, "similarity": round(similarity, 4)})
            if len(results) >= top_k:
                break

        return results

    def find_similar_to_vector(
        self,
        query_vec: np.ndarray,
        top_k: int = 10,
        blocked_flags: set[str] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[dict]:
        """
        Find exercises similar to an arbitrary vector (used by the pair-search
        in the substitution engine, where the query is a residual activation
        vector rather than a specific exercise).
        """
        blocked_flags = blocked_flags or set()
        exclude_ids = exclude_ids or set()

        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = (query_vec / norm).astype(np.float32)

        query_vec = query_vec.reshape(1, -1)

        if FAISS_AVAILABLE and self._index is not None:
            fetch_k = min(len(self._exercises), top_k * 4 + 20)
            similarities, indices = self._index.search(query_vec, fetch_k)
            candidates = [
                (int(idx), float(sim))
                for idx, sim in zip(indices[0], similarities[0])
                if idx >= 0
            ]
        else:
            sims = (self._vectors @ query_vec.T).flatten()
            order = np.argsort(sims)[::-1]
            candidates = [(int(i), float(sims[i])) for i in order]

        results = []
        for idx, similarity in candidates:
            ex = self._exercises[idx]
            if ex["id"] in exclude_ids:
                continue
            if blocked_flags & set(ex.get("joint_stress_flags", [])):
                continue
            results.append({"exercise": ex, "similarity": round(similarity, 4)})
            if len(results) >= top_k:
                break

        return results

    def compute_coverage(
        self,
        target_id: str,
        candidate_ids: list[str],
    ) -> float:
        """
        What fraction of the target exercise's activation profile is covered
        by the union of the candidate exercises?

        Used by the substitution engine to decide if a single exercise or a
        pair is needed, and to populate the explanation layer with numbers.

        Coverage = dot(max(candidate_vecs, axis=0), target_vec)
        where both sides are raw (unnormalised) vectors, clipped to [0,1].
        """
        target_idx = self._id_to_idx.get(target_id)
        if target_idx is None:
            return 0.0

        # Use raw (unnormalised) vectors for coverage
        raw_target = np.array(
            [self._exercises[target_idx]["muscle_activation"].get(m, 0.0) for m in MUSCLES],
            dtype=np.float32,
        )

        if not candidate_ids:
            return 0.0

        candidate_raws = []
        for cid in candidate_ids:
            cidx = self._id_to_idx.get(cid)
            if cidx is None:
                continue
            raw = np.array(
                [self._exercises[cidx]["muscle_activation"].get(m, 0.0) for m in MUSCLES],
                dtype=np.float32,
            )
            candidate_raws.append(raw)

        if not candidate_raws:
            return 0.0

        combined = np.max(np.stack(candidate_raws), axis=0)
        combined = np.clip(combined, 0, 1)

        # Coverage = how much of the target's activation is covered
        target_sum = float(raw_target.sum())
        if target_sum == 0:
            return 0.0
        covered = float(np.minimum(combined, raw_target).sum())
        return min(covered / target_sum, 1.0)

    @property
    def exercises(self) -> list[dict]:
        return self._exercises

    def all_exercises(self) -> list[dict]:
        return list(self._exercises)

    def __len__(self) -> int:
        return len(self._exercises)
