// API response shapes (hand-written from the FastAPI OpenAPI surface).

export interface Injury {
  id: number;
  body_part: string;
  severity: "mild" | "moderate" | "severe";
  pain_type: string | null;
  recovery_expectation_days: number | null;
  notes: string | null;
  is_active: boolean;
  healed_at: string | null;
  created_at: string;
  expected_recovery_date: string | null;
}

export interface User {
  id: number;
  name: string;
  email: string;
  age: number | null;
  weight_kg: number | null;
  height_cm: number | null;
  goals: string[];
  equipment: string[];
  movement_preferences: string[];
  fitness_level: "beginner" | "intermediate" | "advanced";
  experience_level: string;
  days_per_week: number;
  minutes_per_session: number;
  show_personal_records: boolean;
  created_at: string;
  updated_at: string;
  injuries: Injury[];
}

export interface WorkoutExercise {
  id: number;
  exercise_id: string;
  exercise_name: string;
  position: number;
  sets: number;
  reps: string | null;
  duration_seconds: number | null;
  weight_kg: number | null;
  rest_seconds: number;
  notes: string | null;
  feedback: "liked" | "disliked" | "rejected" | null;
  substituted_for_id: string | null;
  substituted_for_name: string | null;
  substitution_note: string | null;
}

export interface WorkoutLog {
  id: number;
  user_id: number;
  name: string | null;
  workout_type: string | null;
  workout_label: string | null;
  source: "daily" | "custom_builder" | string;
  is_template: boolean;
  started_at: string;
  completed_at: string | null;
  notes: string | null;
  exercises: WorkoutExercise[];
}

export interface DayProgram {
  day_index: number;
  date: string;
  is_rest: boolean;
  workout: WorkoutLog | null;
  warnings: string[];
}

export interface WeekProgram {
  days: DayProgram[];
}

export interface LogSummary {
  id: number;
  name: string | null;
  date: string;
  source: string;
  workout_type: string | null;
  workout_label: string | null;
  completed: boolean;
  completed_at: string | null;
  exercise_count: number;
  total_sets: number;
  swap_count: number;
  top_muscles: string[];
  pattern_mix: Record<string, number>;
}

export interface Exercise {
  id: string;
  name: string;
  description: string;
  equipment_required: string[];
  movement_pattern: string;
  force_direction: string;
  joint_stress_flags: string[];
  muscle_activation: Record<string, number>;
}

export type SgState = "eligible" | "preference_penalized" | "cooldown" | "suppressed";

export interface Suggestion {
  exercise: Exercise;
  mechanic: "compound" | "isolation";
  already_added: boolean;
  suggestibility_state: SgState;
  suggestibility_reason: string | null;
}

export interface SuggestionResponse {
  workout_id: number;
  workout_type: string | null;
  total: number;
  offset: number;
  suggestions: Suggestion[];
  facets?: Facets | null;
}

export type Facets = Record<string, Record<string, number>>;

export interface ExerciseListResponse {
  total: number;
  offset: number;
  exercises: Exercise[];
  facets?: Facets;
}

export interface FilterOptions {
  body_part: string[];
  muscle: string[];
  movement_pattern: string[];
  force_direction: string[];
  mechanic: string[];
  equipment_match: string[];
  sort: string[];
}

export interface BuilderOptions {
  workout_types: string[];
  focus_options: { value: string; label: string }[];
  feedback: string[];
  rejection_reasons: string[];
}

export interface MuscleCoverage {
  muscle: string;
  display_name: string;
  activation: number;
}

export interface WorkoutAnalysis {
  exercise_count: number;
  estimated_minutes: number;
  target_minutes: number | null;
  duration_verdict: "short" | "on_target" | "long" | "unknown";
  muscle_coverage: MuscleCoverage[];
  pattern_breakdown: Record<string, number>;
  missing_patterns: string[];
  injury_conflicts: string[];
  warnings: string[];
}

export interface MutationResponse {
  workout: WorkoutLog;
  warnings: string[];
}

// ── Dashboard ──────────────────────────────────────────────
export interface DashSummary {
  range: { start: string; end: string };
  workouts: {
    this_week: number;
    this_month: number;
    in_range: number;
    current_streak_days: number;
    weekly_target: number;
    adherence_pct: number | null;
  };
  training: {
    total_activation_load: number;
    total_sets: number;
    top_body_parts: string[];
    undertrained_body_parts: string[];
    push_pull_ratio: number | null;
    upper_lower_ratio: number | null;
  };
  health: {
    avg_steps_7d: number | null;
    avg_steps_30d: number | null;
    avg_active_calories_7d: number | null;
    avg_sleep_hours_7d: number | null;
    body_weight_change_kg: number | null;
    latest_body_weight_kg: number | null;
  };
  readiness: { score: number; label: string; factors: string[] };
  injuries: { active: string[]; active_count: number };
  personal_records_enabled: boolean;
}

export interface MuscleActivation {
  bucket: string;
  group: "muscle" | "body_part";
  normalize: string;
  columns: string[];
  labels: Record<string, string>;
  buckets: string[];
  series: Record<string, number[]>;
}

export interface VolumeSeries {
  bucket: string;
  buckets: string[];
  workouts: number[];
  sets: number[];
  minutes: number[];
  activation_load: number[];
  by_pattern: Record<string, number[]>;
}

export interface WorkoutCounts {
  bucket: string;
  buckets: string[];
  counts: number[];
  by_source: Record<string, number[]>;
  total: number;
  target: number;
  adherence_pct: number | null;
  current_streak_days: number;
}

export interface Consistency {
  start: string;
  end: string;
  weeks: number;
  counts: Record<string, number>;
  active_days: number;
  total_days: number;
}

export interface Balance {
  by_group: Record<string, number>;
  shares: Record<string, number>;
  push_pull_ratio: number | null;
  upper_lower_ratio: number | null;
  undertrained: string[];
}

export interface Patterns {
  by_pattern_sets: Record<string, number>;
  by_pattern_exercises: Record<string, number>;
  shares: Record<string, number>;
}

export interface Rejections {
  total: number;
  by_reason: Record<string, number>;
  top_exercises: { exercise: string; count: number }[];
  bucket: string;
  buckets: string[];
  counts: number[];
}

export interface Substitutions {
  total_swaps: number;
  workouts_with_swaps: number;
  swap_rate_pct: number | null;
  top_swapped_out: { exercise: string; count: number }[];
}

export interface MetricSeries {
  metric: string;
  dates: string[];
  values: number[];
  rolling_7d: number[];
  summary: { avg: number; min: number; max: number; latest: number; change: number } | Record<string, never>;
}

export interface InjuryTimeline {
  injuries: {
    body_part: string;
    severity: string;
    start: string;
    end: string | null;
    ongoing: boolean;
    duration_days: number;
    workouts_during: number;
    workouts_before_equal_window: number;
  }[];
}

export interface PersonalRecords {
  records: {
    exercise_id: string;
    exercise_name: string;
    best_weight_kg: number;
    achieved_on: string;
    first_weight_kg: number;
    first_on: string;
    gain_kg: number;
    sessions: number;
  }[];
  enabled: boolean;
}

export interface RejectionRow {
  id: number;
  exercise_id: string;
  exercise_name: string;
  reason: string;
  pain_level: number | null;
  pain_type: string | null;
  body_area: string | null;
  note: string | null;
  created_at: string;
}

export interface DailyMetric {
  date: string;
  steps: number | null;
  active_calories: number | null;
  resting_heart_rate: number | null;
  body_weight_kg: number | null;
  sleep_hours: number | null;
  energy_level: number | null;
  notes: string | null;
  updated_at: string | null;
}

// ── Explain (substitution detail) ──────────────────────────
export interface ExplainResponse {
  original: Exercise;
  suggestibility: {
    exercise_id: string;
    state: SgState;
    preference_score: number;
    suppression_reason: string | null;
    blocked_flags: string[];
  };
  substitutes: {
    exercise: Exercise;
    similarity: number;
    coverage: number;
    preference_score: number;
    rank_score: number;
    explanation: string;
    complements?: { exercise: Exercise; combined_coverage: number }[];
  }[];
}
