"""
One-off test: run the real explanation-service prompt against several
candidate Gemini model names and print each output for comparison.

Usage (from backend/):
    python scripts/test_gemini_explanation.py

Requires LLM_PROVIDER=gemini and GEMINI_API_KEY set in backend/.env.
"""

import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.explanation_service import _SYSTEM_PROMPT, _FEW_SHOT, _build_user_message
from app.services.llm_client import llm_chat
from app.services.substitution_engine import Substitute
from app.services.suggestibility_engine import SuggestibilityResult, SuggestibilityState

CANDIDATE_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
]

original = {
    "name": "Push-up",
    "force_direction": "against_gravity",
    "equipment_required": ["bodyweight"],
    "muscle_activation": {
        "chest": 0.85,
        "triceps": 0.70,
        "anterior_deltoid": 0.65,
        "core": 0.30,
    },
}

substitute = Substitute(
    exercise={
        "id": "ex_bench_press",
        "name": "Barbell Bench Press",
        "force_direction": "supported",
        "equipment_required": ["barbell", "bench"],
        "muscle_activation": {"chest": 0.80, "triceps": 0.65, "anterior_deltoid": 0.60},
    },
    similarity=0.960,
    coverage=0.933,
    preference_score=1.0,
    rank_score=0.960,
)

sg_result = SuggestibilityResult(
    exercise_id="ex_pushup",
    state=SuggestibilityState.SUPPRESSED,
    preference_score=1.0,
    suppression_reason="right shoulder injury — joint stress: high_shoulder_flexion_under_load; force direction 'against_gravity' restricted",
)

complements = [
    {
        "exercise": {"id": "ex_lateral_raise", "name": "Dumbbell Lateral Raise"},
        "combined_coverage": 0.97,
    }
]


async def main():
    user_message = _build_user_message(original, substitute, sg_result, complements)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_FEW_SHOT,
        {"role": "user", "content": user_message},
    ]

    for model in CANDIDATE_MODELS:
        settings.gemini_model = model
        print(f"\n{'=' * 70}\nMODEL: {model}\n{'=' * 70}")
        try:
            response = await llm_chat(messages=messages, temperature=0.5, max_tokens=800)
            print(response.choices[0].message.content)
        except Exception:
            print("ERROR (full traceback):")
            traceback.print_exc()


if __name__ == "__main__":
    print(f"LLM_PROVIDER = {settings.llm_provider}")
    if settings.llm_provider.lower() != "gemini":
        print("WARNING: LLM_PROVIDER is not 'gemini' in .env — set it before running this test.")
    asyncio.run(main())
