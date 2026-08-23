"""
Explanation service — Stage 6.

The LLM narrates pre-computed substitution data in plain English.
It does NOT make safety or similarity decisions — those happen in
SuggestibilityEngine and SubstitutionEngine. The LLM only writes the sentence.

This design keeps safety logic deterministic and testable, while
giving the user a natural-language reason for every recommendation.
"""

from __future__ import annotations

from app.services.llm_client import llm_chat
from app.services.substitution_engine import Substitute
from app.services.suggestibility_engine import SuggestibilityResult, SuggestibilityState

_SYSTEM_PROMPT = """\
You are a knowledgeable fitness coach writing brief, clear exercise substitution explanations.
You receive structured data about why an exercise was swapped and what the substitute offers.
Write 2–3 plain sentences. No bullet points, no headers, no markdown.
Be specific — use the actual exercise names and the numbers you are given.
Never invent information that is not in the data you receive.\
"""

_FEW_SHOT = [
    {
        "role": "user",
        "content": """\
Original exercise: Push-up
Substitute: Barbell Bench Press
Similarity: 0.960 (96% muscle match)
Coverage: 0.933 (substitute delivers 93% of original's total muscle activation)
Suppression reason: right shoulder injury — joint stress: high_shoulder_flexion_under_load; force direction 'against_gravity' restricted
Preference score: 1.0 (no dislikes logged)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "Push-ups are blocked because your right shoulder injury restricts movements where "
            "you push your bodyweight against gravity — the exact load pattern of a push-up. "
            "Barbell Bench Press works the same muscles at 96% similarity and delivers 93% of "
            "your usual chest activation, but with the bench supporting your body so the injured "
            "shoulder carries only the bar weight, not your full bodyweight."
        ),
    },
    {
        "role": "user",
        "content": """\
Original exercise: Overhead Press (Military Press)
Substitute: Lateral Raise
Similarity: 0.810 (81% muscle match)
Coverage: 0.774 (substitute delivers 77% of original's total muscle activation)
Suppression reason: right shoulder injury — joint stress: rotator_cuff_load, shoulder_impingement_risk; force direction 'against_gravity' restricted
Preference score: 0.70 (dont_like logged 2 times)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "Overhead pressing is blocked because it loads the rotator cuff and shoulder joint "
            "directly overhead — contraindicated during your right shoulder recovery. "
            "Lateral Raises hit 81% of the same muscles and can be done with light resistance "
            "bands at a safe angle, though they cover 77% of the total shoulder activation so "
            "you may want to pair them with a rear-delt exercise to fill the gap. "
            "Note: you have logged this exercise as disliked twice, so it's ranked lower "
            "in your suggestions."
        ),
    },
]


def _build_user_message(
    original: dict,
    substitute: Substitute,
    sg_result: SuggestibilityResult,
) -> str:
    lines = [
        f"Original exercise: {original['name']}",
        f"Substitute: {substitute.exercise['name']}",
        f"Similarity: {substitute.similarity:.3f} ({int(substitute.similarity * 100)}% muscle match)",
        f"Coverage: {substitute.coverage:.3f} (substitute delivers {int(substitute.coverage * 100)}% of original's total muscle activation)",
    ]

    if sg_result.suppression_reason:
        lines.append(f"Suppression reason: {sg_result.suppression_reason}")
    elif sg_result.state == SuggestibilityState.COOLDOWN:
        lines.append(f"Cooldown reason: {sg_result.suppression_reason or 'temporary soreness/fatigue'}")

    score = sg_result.preference_score
    if score < 1.0:
        lines.append(f"Preference score: {score:.2f} (some dislikes or difficulty mismatches logged)")
    else:
        lines.append("Preference score: 1.0 (no dislikes logged)")

    return "\n".join(lines)


async def explain_substitution(
    original: dict,
    substitute: Substitute,
    sg_result: SuggestibilityResult,
) -> str:
    """
    Generate a plain-English explanation for a single substitution.

    Returns the explanation string. On LLM error, returns a safe fallback message
    so the rest of the API response still reaches the user.
    """
    user_message = _build_user_message(original, substitute, sg_result)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_FEW_SHOT,
        {"role": "user", "content": user_message},
    ]

    try:
        response = await llm_chat(messages=messages, temperature=0.4, max_tokens=300)
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return (
            f"{original['name']} was substituted with {substitute.exercise['name']} "
            f"({int(substitute.similarity * 100)}% muscle match, "
            f"{int(substitute.coverage * 100)}% activation coverage)."
        )


async def explain_substitution_set(
    original: dict,
    substitutes: list[Substitute],
    sg_result: SuggestibilityResult,
) -> list[dict]:
    """
    Explain all substitutes for one blocked exercise.
    Returns a list of dicts: [{exercise, similarity, coverage, explanation}, ...]
    """
    results = []
    for sub in substitutes:
        explanation = await explain_substitution(original, sub, sg_result)
        results.append({
            "exercise": sub.exercise,
            "similarity": sub.similarity,
            "coverage": sub.coverage,
            "preference_score": sub.preference_score,
            "rank_score": sub.rank_score,
            "explanation": explanation,
        })
    return results
