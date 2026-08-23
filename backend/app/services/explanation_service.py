"""
Explanation service — Stage 6.

The LLM narrates pre-computed substitution data in plain English with
the tone of a personal trainer. All safety and ranking decisions happen
in SuggestibilityEngine and SubstitutionEngine — the LLM only writes the text.
"""

from __future__ import annotations

from app.services.llm_client import llm_chat
from app.services.substitution_engine import Substitute
from app.services.suggestibility_engine import SuggestibilityResult, SuggestibilityState

_SYSTEM_PROMPT = """\
You are a knowledgeable, encouraging personal trainer writing exercise substitution explanations.
Your job is to explain — in the tone of a supportive coach — why an exercise was swapped, \
what the substitute offers, and how to approach it safely.

Rules:
- Write 3–5 sentences. No bullet points, no headers, no markdown.
- Use the actual exercise names and the numbers you are given. Never invent data.
- Reference specific muscles when relevant (e.g. "chest, triceps, anterior deltoid").
- Explain the injury/restriction in plain language — not medical jargon.
- Always include a brief safety reminder (e.g. if you feel pain, stop).
- If complement exercises are listed, name them explicitly and say the user can \
  pair the primary substitute with any one of them to recover the missing activation. \
  Say something like "to cover the remaining X%, pair it with [complement names]."
- If no complements are listed and coverage is below 85%, note the gap briefly.
- If the original exercise could be attempted in a modified/safer form, \
  briefly suggest how (e.g. on knees, lighter weight, reduced range of motion) — \
  but only if the original is blocked by preference or cooldown, not an active injury.
- Keep the tone warm, direct, and practical — like a trainer who knows your history.\
"""

_FEW_SHOT = [
    {
        "role": "user",
        "content": """\
Original exercise: Push-up (against_gravity, bodyweight)
Substitute: Barbell Bench Press (supported, barbell + bench)
Similarity: 0.960 (96% muscle match)
Coverage: 0.933 (93% of push-up's total muscle activation)
Suppression reason: right shoulder injury — joint stress: high_shoulder_flexion_under_load; force direction 'against_gravity' restricted
Preference score: 1.0
Top muscles matched: chest (0.85), triceps (0.70), anterior_deltoid (0.65)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "I'm swapping push-ups for the Barbell Bench Press while your right shoulder is healing. "
            "The issue with push-ups isn't the muscles — it's the mechanics: you're pushing your entire bodyweight against gravity, "
            "which puts a lot of stress on the rotator cuff and shoulder joint in exactly the way your injury doesn't like right now. "
            "On the bench, the rack takes that load off — you're just moving the bar, not your whole body — so your chest, triceps, "
            "and front delts get 96% of the same stimulus with 93% of the activation, at a fraction of the shoulder stress. "
            "Start lighter than you think you need to, keep your shoulder blades pinched back throughout, and rack it immediately "
            "if you feel any discomfort in that shoulder."
        ),
    },
    {
        "role": "user",
        "content": """\
Original exercise: Pull-up (against_gravity, bodyweight)
Substitute: Lat Pulldown (supported, cable machine)
Similarity: 0.945 (94% muscle match)
Coverage: 0.902 (90% of pull-up's total muscle activation)
Suppression reason: Cooldown until tomorrow (too_sore 1 day ago)
Preference score: 1.0
Top muscles matched: lats (0.90), rhomboids (0.60), biceps (0.55)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "Your lats are still recovering from yesterday's session, so I'm giving them a gentler ride today with the Lat Pulldown. "
            "It hits the same primary muscles — lats, rhomboids, and biceps — at 94% similarity and 90% of your usual pull-up activation, "
            "but you control the weight, which means you can ease up as needed and avoid grinding through soreness. "
            "Keep the weight moderate, focus on the squeeze at the bottom, and don't let your ego load the stack. "
            "If you're feeling decent by tomorrow, pull-ups will be back in rotation — but if you still feel that tightness, "
            "give it one more day on the machine."
        ),
    },
]


def _top_muscles(muscle_activation: dict, n: int = 4) -> str:
    """Return a comma-separated string of the top n muscles by activation value."""
    top = sorted(
        [(m, v) for m, v in muscle_activation.items() if v > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:n]
    return ", ".join(f"{m.replace('_', ' ')} ({v})" for m, v in top)


def _build_user_message(
    original: dict,
    substitute: Substitute,
    sg_result: SuggestibilityResult,
    complements: list[dict] | None = None,
) -> str:
    lines = [
        f"Original exercise: {original['name']} ({original.get('force_direction', 'unknown')}, {', '.join(original.get('equipment_required', ['unknown']))})",
        f"Substitute: {substitute.exercise['name']} ({substitute.exercise.get('force_direction', 'unknown')}, {', '.join(substitute.exercise.get('equipment_required', ['unknown']))})",
        f"Similarity: {substitute.similarity:.3f} ({int(substitute.similarity * 100)}% muscle match)",
        f"Coverage: {substitute.coverage:.3f} ({int(substitute.coverage * 100)}% of {original['name']}'s total muscle activation)",
    ]

    if sg_result.suppression_reason:
        lines.append(f"Suppression reason: {sg_result.suppression_reason}")
    elif sg_result.state == SuggestibilityState.COOLDOWN and sg_result.cooldown_until:
        lines.append(f"Cooldown reason: {sg_result.suppression_reason or 'temporary soreness/fatigue'}")

    score = sg_result.preference_score
    if score < 1.0:
        lines.append(f"Preference score: {score:.2f} (user has logged dislikes or difficulty feedback for the original)")
    else:
        lines.append("Preference score: 1.0 (no dislikes logged)")

    orig_muscles = _top_muscles(original.get("muscle_activation", {}))
    if orig_muscles:
        lines.append(f"Top muscles in original: {orig_muscles}")

    if complements:
        gap_pct = 100 - int(substitute.coverage * 100)
        names = ", ".join(c["exercise"]["name"] for c in complements)
        best_coverage = int(complements[0]["combined_coverage"] * 100)
        lines.append(
            f"Complement options (to cover the remaining {gap_pct}%): {names}. "
            f"Pairing the substitute with the best complement reaches {best_coverage}% total coverage."
        )

    return "\n".join(lines)


async def explain_substitution(
    original: dict,
    substitute: Substitute,
    sg_result: SuggestibilityResult,
    complements: list[dict] | None = None,
) -> str:
    """
    Generate a plain-English personal-trainer explanation for a single substitution.

    On LLM error, returns a factual fallback so the API response is never empty.
    """
    user_message = _build_user_message(original, substitute, sg_result, complements)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *_FEW_SHOT,
        {"role": "user", "content": user_message},
    ]

    try:
        response = await llm_chat(messages=messages, temperature=0.5, max_tokens=500)
        return response.choices[0].message.content.strip()
    except Exception:
        if complements:
            gap_pct = 100 - int(substitute.coverage * 100)
            names = ", ".join(c["exercise"]["name"] for c in complements[:3])
            coverage_note = f" To cover the remaining {gap_pct}%, pair it with one of: {names}."
        elif substitute.coverage < 0.85:
            coverage_note = f" Consider adding a complementary exercise to cover the remaining {100 - int(substitute.coverage * 100)}%."
        else:
            coverage_note = ""
        return (
            f"{original['name']} has been swapped for {substitute.exercise['name']} "
            f"({int(substitute.similarity * 100)}% muscle match, "
            f"{int(substitute.coverage * 100)}% activation coverage).{coverage_note} "
            f"Stop immediately if you feel any pain or discomfort."
        )


async def explain_substitution_set(
    original: dict,
    substitutes: list[Substitute],
    sg_result: SuggestibilityResult,
    complements_per_sub: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """
    Explain all substitutes for one blocked exercise.
    Returns [{exercise, similarity, coverage, preference_score, rank_score, explanation, complements}, ...]
    complements_per_sub maps substitute exercise_id -> list of complement dicts.
    """
    complements_per_sub = complements_per_sub or {}
    results = []
    for sub in substitutes:
        complements = complements_per_sub.get(sub.exercise["id"])
        explanation = await explain_substitution(original, sub, sg_result, complements)
        result = {
            "exercise": sub.exercise,
            "similarity": sub.similarity,
            "coverage": sub.coverage,
            "preference_score": sub.preference_score,
            "rank_score": sub.rank_score,
            "explanation": explanation,
        }
        if complements:
            result["complements"] = [
                {
                    "exercise": c["exercise"],
                    "combined_coverage": c["combined_coverage"],
                }
                for c in complements
            ]
        results.append(result)
    return results
