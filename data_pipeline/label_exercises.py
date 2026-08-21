"""
data_pipeline/label_exercises.py
---------------------------------
Offline script: reads exercise_names_to_label.txt, calls Groq (or Ollama)
with few-shot examples, validates the returned JSON, and appends new exercises
to backend/app/data/exercises.json.

Usage:
  cd data_pipeline
  python label_exercises.py                   # label all pending exercises
  python label_exercises.py --limit 10        # label first 10 (good for testing)
  python label_exercises.py --dry-run         # print prompts without calling LLM

Design:
  - Each LLM call labels exactly ONE exercise (simpler validation, cheaper retries).
  - Few-shot examples are sampled from the hand-labeled batch in exercises.json.
  - If the LLM response fails validation, we retry up to MAX_RETRIES times.
  - After each successful label, the file is saved (so a crash doesn't lose work).
  - Already-labeled exercises are skipped automatically (idempotent).
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

def _parse_retry_after(msg: str) -> float:
    """Extract seconds to wait from a 429 message (Groq or Google format)."""
    # Groq: "Please try again in 16m32.304s"
    m = re.search(r"try again in (?:(\d+)m)?(?:([\d.]+)s)?", msg)
    if m and (m.group(1) or m.group(2)):
        minutes = int(m.group(1) or 0)
        seconds = float(m.group(2) or 0)
        return minutes * 60 + seconds + 2
    # Google: "retryDelay: '9s'" or "Please retry in 9.9s"
    m = re.search(r"retry[^'\"]*['\"]?([\d.]+)s", msg)
    if m:
        return float(m.group(1)) + 2
    return 15.0  # conservative default

# Add the backend to sys.path so we can import MUSCLES constants
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.data.muscles import (
    FORCE_DIRECTIONS,
    JOINT_STRESS_FLAGS,
    MOVEMENT_PATTERNS,
    MUSCLE_SET,
    MUSCLES,
)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / "backend" / ".env")
except ImportError:
    pass  # dotenv optional; env vars may already be set

# ── Config ─────────────────────────────────────────────────────────────────────

EXERCISES_JSON = REPO_ROOT / "backend" / "app" / "data" / "exercises.json"
NAMES_FILE = Path(__file__).parent / "exercise_names_to_label.txt"

MAX_RETRIES = 1
FEW_SHOT_COUNT = 0       # 0 examples = ~1100 tokens/req vs ~3300; fits ~180 per TPD window
BATCH_SLEEP_SECONDS = 3  # polite delay between API calls (helps with Groq free-tier RPM limits)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def _build_client() -> OpenAI:
    if LLM_PROVIDER == "groq":
        return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    if LLM_PROVIDER == "gemini":
        return OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return OpenAI(api_key="ollama", base_url=f"{OLLAMA_BASE_URL}/v1")


def _active_model() -> str:
    if LLM_PROVIDER == "groq":
        return GROQ_MODEL
    if LLM_PROVIDER == "gemini":
        return GEMINI_MODEL
    return OLLAMA_MODEL


# ── Load / save helpers ────────────────────────────────────────────────────────

def load_dataset() -> dict:
    with open(EXERCISES_JSON) as f:
        return json.load(f)


def save_dataset(dataset: dict) -> None:
    with open(EXERCISES_JSON, "w") as f:
        json.dump(dataset, f, indent=2)
    print(f"  [saved] {EXERCISES_JSON.name} now has {len(dataset['exercises'])} exercises")


def existing_ids(dataset: dict) -> set[str]:
    return {ex["id"] for ex in dataset["exercises"]}


def existing_names(dataset: dict) -> set[str]:
    return {ex["name"].lower() for ex in dataset["exercises"]}


def load_pending_names() -> list[str]:
    lines = NAMES_FILE.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


# ── Prompt engineering ────────────────────────────────────────────────────────

def _exercise_to_example_block(ex: dict) -> str:
    """Format a single hand-labeled exercise as a JSON string for the few-shot block."""
    return json.dumps({
        "id": ex["id"],
        "name": ex["name"],
        "description": ex["description"],
        "equipment_required": ex["equipment_required"],
        "movement_pattern": ex["movement_pattern"],
        "force_direction": ex["force_direction"],
        "joint_stress_flags": ex["joint_stress_flags"],
        "muscle_activation": ex["muscle_activation"],
    }, indent=2)


def build_prompt(target_name: str, examples: list[dict]) -> list[dict]:
    """
    Build a chain-of-thought few-shot prompt to label a single exercise.

    The system prompt explains the schema in detail. The user message provides
    few-shot examples and asks for the target exercise.
    """
    muscles_list = json.dumps(MUSCLES)
    movement_options = sorted(MOVEMENT_PATTERNS)
    force_options = sorted(FORCE_DIRECTIONS)
    stress_options = sorted(JOINT_STRESS_FLAGS)

    system_prompt = f"""You are an expert exercise physiologist and sports scientist.
Your task is to label exercises with precise, biomechanically accurate data for a fitness application.

Return ONLY valid JSON. No explanation, no markdown fences, no other text.

## Schema

{{
  "id": "<snake_case_unique_id>",
  "name": "<full exercise name>",
  "description": "<1-2 sentence biomechanical description including what muscles work and why>",
  "equipment_required": ["<from: bodyweight, barbell, dumbbells, kettlebell, pull_up_bar, resistance_bands, cables, machines, bench, squat_rack, trx>"],
  "movement_pattern": "<exactly one of: {movement_options}>",
  "force_direction": "<exactly one of: {force_options}>",
  "joint_stress_flags": ["<zero or more from: {stress_options}>"],
  "muscle_activation": {{
    <ALL {len(MUSCLES)} muscles from the canonical list, each with a float 0.0–1.0>
  }}
}}

## Canonical muscle list (ALL must be present in muscle_activation)
{muscles_list}

## Activation scale
- 0.9–1.0: primary mover
- 0.6–0.8: strong secondary / major stabilizer
- 0.3–0.5: moderate stabilizer
- 0.1–0.2: minor activation / postural stabilizer
- 0.0: not meaningfully recruited

## Force direction definitions
- against_gravity: bodyweight or free overhead — joints bear gravity load (e.g. push-up, pull-up, overhead press)
- supported: body supported by bench/seat — joints bear external weight only (e.g. bench press, leg press)
- horizontal: primary resistance is horizontal (e.g. rows, cable flies, face pull)
- vertical: primary resistance is vertical downward but body is supported (e.g. lat pulldown, tricep pushdown)

## Rules
1. Every muscle in the canonical list MUST appear as a key in muscle_activation.
2. Values must be floats between 0.0 and 1.0 (two decimal places max).
3. movement_pattern must be exactly one of the options listed.
4. force_direction must be exactly one of the options listed.
5. joint_stress_flags must be a subset of the listed options (can be empty []).
6. id must be snake_case, lowercase, no spaces.
7. Return ONLY the JSON object — no extra text, no markdown.
"""

    example_blocks = "\n\n---\n\n".join(
        f"Example {i+1}:\n{_exercise_to_example_block(ex)}"
        for i, ex in enumerate(examples)
    )

    user_prompt = f"""Here are {len(examples)} verified examples from our dataset:

{example_blocks}

---

Now label this exercise using the same schema:
Exercise name: {target_name}

Return ONLY the JSON object.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ── Validation ────────────────────────────────────────────────────────────────

def validate_exercise(data: dict, existing_ids_set: set[str]) -> list[str]:
    """Return a list of error strings (empty = valid)."""
    errors = []

    required_fields = ["id", "name", "description", "equipment_required",
                       "movement_pattern", "force_direction", "joint_stress_flags",
                       "muscle_activation"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing field: {field}")

    if errors:
        return errors

    # movement_pattern
    if data["movement_pattern"] not in MOVEMENT_PATTERNS:
        errors.append(f"Invalid movement_pattern: {data['movement_pattern']!r}. Valid: {MOVEMENT_PATTERNS}")

    # force_direction
    if data["force_direction"] not in FORCE_DIRECTIONS:
        errors.append(f"Invalid force_direction: {data['force_direction']!r}. Valid: {FORCE_DIRECTIONS}")

    # joint_stress_flags
    bad_flags = set(data["joint_stress_flags"]) - JOINT_STRESS_FLAGS
    if bad_flags:
        errors.append(f"Unknown joint_stress_flags: {bad_flags}. Valid: {JOINT_STRESS_FLAGS}")

    # muscle_activation — all 22 muscles must be present
    activation = data.get("muscle_activation", {})
    missing = MUSCLE_SET - set(activation.keys())
    extra = set(activation.keys()) - MUSCLE_SET
    if missing:
        errors.append(f"muscle_activation missing muscles: {sorted(missing)}")
    if extra:
        errors.append(f"muscle_activation has unknown muscles: {sorted(extra)}")

    # All values must be floats in [0, 1]
    for muscle, value in activation.items():
        if not isinstance(value, (int, float)):
            errors.append(f"muscle_activation[{muscle!r}] is not a number: {value!r}")
        elif not (0.0 <= float(value) <= 1.0):
            errors.append(f"muscle_activation[{muscle!r}] = {value} is out of range [0, 1]")

    # id format
    if not re.match(r"^[a-z0-9][a-z0-9_]*$", data.get("id", "")):
        errors.append(f"id {data.get('id')!r} must be snake_case (lowercase, underscores)")

    return errors


# ── Main labeling loop ────────────────────────────────────────────────────────

def label_exercise(
    name: str,
    dataset: dict,
    client: OpenAI,
    dry_run: bool = False,
) -> dict | None:
    """
    Label a single exercise. Returns the labeled dict or None on failure.
    Picks FEW_SHOT_COUNT examples from the already-labeled batch, biased
    toward exercises with similar movement patterns when possible.
    """
    # Sample few-shot examples
    manual = [ex for ex in dataset["exercises"] if ex.get("labeling_source") == "manual"]
    examples = random.sample(manual, min(FEW_SHOT_COUNT, len(manual)))

    messages = build_prompt(name, examples)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — would label: {name}")
        print("System:", messages[0]["content"][:300], "...")
        print("User (last 200 chars):", messages[1]["content"][-200:])
        return None

    existing = existing_ids(dataset)
    model = _active_model()
    attempts_used = 0
    raw = ""

    while attempts_used < MAX_RETRIES:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,   # low temp for consistent structured output
                max_tokens=2048,
            )
            raw = response.choices[0].message.content.strip()

            # Extract the first complete {...} block — handles thinking-model
            # prefixes, markdown fences, and any trailing text the model adds.
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                raise json.JSONDecodeError("No JSON object found", raw, 0)
            raw = raw[start:end + 1]

            data = json.loads(raw)
            errors = validate_exercise(data, existing)

            if errors:
                attempts_used += 1
                print(f"  [attempt {attempts_used}] Validation errors:")
                for e in errors:
                    print(f"    - {e}")
                continue

            # Normalize floats to 2 decimal places
            data["muscle_activation"] = {
                m: round(float(v), 2)
                for m, v in data["muscle_activation"].items()
            }
            data["labeling_source"] = "llm"
            return data

        except json.JSONDecodeError as e:
            attempts_used += 1
            print(f"  [attempt {attempts_used}] JSON parse error: {e}")
            print(f"  Raw response: {raw[:300]!r}")
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate_limit" in msg.lower():
                wait = _parse_retry_after(msg)
                print(f"  [rate limit] sleeping {wait:.0f}s then retrying...")
                time.sleep(wait)
            elif "503" in msg or "UNAVAILABLE" in msg or "high demand" in msg.lower():
                print(f"  [503 overload] sleeping 30s then retrying...")
                time.sleep(30)
            else:
                attempts_used += 1
                print(f"  [attempt {attempts_used}] API error: {e}")
                time.sleep(5)

    print(f"  [FAILED] Could not label '{name}' after {MAX_RETRIES} attempts.")
    return None


def main():
    parser = argparse.ArgumentParser(description="Label exercises using an LLM")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of exercises to label (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts without calling the LLM")
    args = parser.parse_args()

    dataset = load_dataset()
    already_labeled = existing_names(dataset)

    pending = [
        name for name in load_pending_names()
        if name.lower() not in already_labeled
    ]

    if args.limit:
        pending = pending[:args.limit]

    print(f"Exercises already labeled: {len(dataset['exercises'])}")
    print(f"Exercises pending:         {len(pending)}")

    if not pending:
        print("Nothing to do — all exercises are already labeled.")
        return

    if not args.dry_run:
        if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
            print("ERROR: GROQ_API_KEY is not set. Add it to backend/.env")
            sys.exit(1)

    client = _build_client() if not args.dry_run else None

    labeled_count = 0
    failed = []

    for i, name in enumerate(pending, 1):
        print(f"\n[{i}/{len(pending)}] Labeling: {name}")
        result = label_exercise(name, dataset, client, dry_run=args.dry_run)

        if result:
            dataset["exercises"].append(result)
            save_dataset(dataset)
            labeled_count += 1

            # Polite delay to avoid rate limiting
            if i < len(pending):
                time.sleep(BATCH_SLEEP_SECONDS)
        elif not args.dry_run:
            failed.append(name)

    print(f"\n{'='*60}")
    print(f"Done. Labeled: {labeled_count}  |  Failed: {len(failed)}")
    if failed:
        print("Failed exercises (add manually or re-run):")
        for name in failed:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
