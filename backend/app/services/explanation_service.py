"""
Explanation service — Stage 6.

The LLM narrates pre-computed substitution data as a short, coach-voiced
tooltip (2-3 sentences, stats woven in as percentages). All safety and
ranking decisions happen in SuggestibilityEngine and SubstitutionEngine —
the LLM only writes the text.
"""

from __future__ import annotations

import json

from app.services.llm_client import llm_chat
from app.services.substitution_engine import Substitute
from app.services.suggestibility_engine import SuggestibilityResult, SuggestibilityState

_SYSTEM_PROMPT = """\
You are a knowledgeable, encouraging personal trainer writing short exercise-swap explanations \
for a tap-to-reveal tooltip in a fitness app. The user taps a suggested exercise to see what got \
swapped out and why — write it in your voice as their coach, not a clinical printout.

Rules:
- 2–3 sentences total, tight enough to read at a glance. Warm, direct, first-person ("I swapped...", \
  "your..."). No headers, no bullet points, no markdown, no exclamation points.
- Weave the numbers into the first sentence naturally — similarity %, coverage %, and the top 2–3 \
  muscles involved as percentages (e.g. "chest at 85%"). Don't just list stats.
- One sentence on why the swap makes sense given the injury/cooldown/preference reason, in plain \
  language — not medical jargon.
- If complements are listed, name them and mention the combined coverage % as how to make up the gap.
- If no complements are listed and coverage is below 85%, note the gap briefly.
- Close with a short, encouraging safety cue in coach voice (not a clinical command).
- If the original is blocked by preference or cooldown (not an active injury), you may suggest a \
  modified/safer version of the original instead of the safety cue.
- Never invent data not given.\
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
Top muscles matched: chest (85%), triceps (70%), anterior_deltoid (65%)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "I'm moving you from push-ups to the Barbell Bench Press — it's a 96% match at 93% coverage, "
            "still hitting chest (85%), triceps (70%), and front delts (65%) just like the push-up did. "
            "The bench takes your bodyweight out of the equation, so that against-gravity load on your right "
            "shoulder is gone. Start light, keep your shoulder blades pinned back, and ease off if that shoulder talks to you."
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
Top muscles matched: lats (90%), rhomboids (60%), biceps (55%)\
""",
    },
    {
        "role": "assistant",
        "content": (
            "Swapping pull-ups for the Lat Pulldown today — 94% similarity, 90% coverage, still hitting lats (90%), "
            "rhomboids (60%), and biceps (55%). You control the weight on the stack, so you can ease up instead of "
            "grinding through yesterday's soreness. Keep it moderate and we'll get you back on the bar once that tightness clears up."
        ),
    },
]


def _top_muscles(muscle_activation: dict, n: int = 4) -> str:
    """Return a comma-separated string of the top n muscles by activation value, as percentages."""
    top = sorted(
        [(m, v) for m, v in muscle_activation.items() if v > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:n]
    return ", ".join(f"{m.replace('_', ' ')} ({int(round(v * 100))}%)" for m, v in top)


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


def _fallback_note(
    original: dict,
    substitute: Substitute,
    complements: list[dict] | None = None,
) -> str:
    """Factual, LLM-free explanation — used when the model errors or is rate-limited."""
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
        response = await llm_chat(messages=messages, temperature=0.5, max_tokens=700)
        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_note(original, substitute, complements)


_BATCH_SYSTEM_PROMPT = _SYSTEM_PROMPT + """

You will be given SEVERAL numbered swaps at once (SWAP 1, SWAP 2, ...). Write one \
explanation for each, following all the rules above for every one. Respond with a \
single JSON object of the form {"explanations": [{"n": 1, "text": "..."}, {"n": 2, \
"text": "..."}, ...]} — one entry per swap, in order, "n" matching the swap number. \
No prose outside the JSON.\
"""


async def explain_substitutions_batch(
    swaps: list[dict],
) -> list[str]:
    """
    Narrate a whole day's worth of swaps in ONE LLM call.

    swaps: [{"original": dict, "substitute": Substitute,
             "sg_result": SuggestibilityResult, "complements": list|None}, ...]

    Returns a list of note strings aligned to `swaps`. Any swap the model
    doesn't return text for (or if the whole call fails / can't be parsed)
    falls back to `_fallback_note` for that item — never an empty string.
    """
    if not swaps:
        return []

    fallbacks = [
        _fallback_note(s["original"], s["substitute"], s.get("complements"))
        for s in swaps
    ]
    if len(swaps) == 1:
        s = swaps[0]
        return [await explain_substitution(
            s["original"], s["substitute"], s["sg_result"], s.get("complements")
        )]

    blocks = []
    for i, s in enumerate(swaps, start=1):
        body = _build_user_message(
            s["original"], s["substitute"], s["sg_result"], s.get("complements")
        )
        blocks.append(f"SWAP {i}:\n{body}")
    user_message = "\n\n".join(blocks)

    messages = [
        {"role": "system", "content": _BATCH_SYSTEM_PROMPT},
        *_FEW_SHOT,
        {"role": "user", "content": user_message},
    ]

    try:
        response = await llm_chat(
            messages=messages,
            temperature=0.5,
            max_tokens=400 + 320 * len(swaps),
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        entries = parsed["explanations"] if isinstance(parsed, dict) else parsed
        by_n: dict[int, str] = {}
        for idx, entry in enumerate(entries, start=1):
            if isinstance(entry, str):
                by_n[idx] = entry.strip()
            else:
                n = int(entry.get("n", idx))
                by_n[n] = str(entry.get("text", "")).strip()
        return [by_n.get(i + 1) or fallbacks[i] for i in range(len(swaps))]
    except Exception:
        return fallbacks


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
