import type {
  Balance, BuilderOptions, Consistency, DailyMetric, DashSummary, DayProgram,
  Exercise, ExerciseListResponse, ExplainResponse, FilterOptions,
  InjuryTimeline, LogSummary, MetricSeries, MuscleActivation, MutationResponse,
  Patterns, PersonalRecords, RejectionRow, Rejections, Substitutions, SuggestionResponse,
  User, VolumeSeries, WeekProgram, WorkoutAnalysis, WorkoutCounts, WorkoutLog,
} from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => p.append(k, String(item)));
    else p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function req<T>(path: string, opts: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, ...init } = opts;
  const res = await fetch(`${API_BASE}${path}${qs(query)}`, {
    ...init,
    headers: init.body ? { "Content-Type": "application/json", ...init.headers } : init.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail
        : Array.isArray(body?.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
        : JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (data: unknown): RequestInit => ({ body: JSON.stringify(data) });

/** URL for an <img>/inline-SVG asset endpoint (muscle map, chart PNGs). */
export function assetUrl(path: string, query?: Query): string {
  return `${API_BASE}${path}${qs(query)}`;
}

// ── Profile ────────────────────────────────────────────────
export const api = {
  getUser: (id: number) => req<User>(`/users/${id}`),
  listUsers: () => req<User[]>(`/users`),
  createUser: (body: Partial<User> & { name: string; email: string }) =>
    req<User>(`/users`, { method: "POST", ...json(body) }),
  updateUser: (id: number, body: Partial<User>) =>
    req<User>(`/users/${id}`, { method: "PATCH", ...json(body) }),
  deleteUser: (id: number) => req<void>(`/users/${id}`, { method: "DELETE" }),

  addInjury: (id: number, body: Record<string, unknown>) =>
    req(`/users/${id}/injuries`, { method: "POST", ...json(body) }),
  healInjury: (id: number, injuryId: number) =>
    req(`/users/${id}/injuries/${injuryId}/heal`, { method: "POST" }),
  deleteInjury: (id: number, injuryId: number) =>
    req(`/users/${id}/injuries/${injuryId}`, { method: "DELETE" }),

  // ── Exercises ────────────────────────────────────────────
  exercises: (query: Query) => req<ExerciseListResponse>(`/exercises`, { query }),
  exercise: (exId: string) => req<Exercise>(`/exercises/${exId}`),
  filterOptions: () => req<FilterOptions>(`/exercises/filters`),

  // ── Suggestibility / substitution ───────────────────────
  explain: (id: number, exId: string) => req<ExplainResponse>(`/users/${id}/explain/${exId}`),
  /** Fast, no-LLM substitute list (similarity + coverage only). */
  substitutes: (id: number, exId: string, topK = 4) =>
    req<{ exercise: Exercise; similarity: number; coverage: number; preference_score: number; rank_score: number }[]>(
      `/users/${id}/substitute/${exId}`, { query: { top_k: topK } }),
  suggestibilityBatch: (id: number, exerciseIds: string[]) =>
    req<{ exercise_id: string; state: string; suppression_reason: string | null }[]>(
      `/users/${id}/suggestibility/batch`, { method: "POST", body: JSON.stringify({ exercise_ids: exerciseIds }) }),
  rejections: (id: number) => req<RejectionRow[]>(`/users/${id}/rejections`),
  deleteRejection: (id: number, rejectionId: number) =>
    req(`/users/${id}/rejections/${rejectionId}`, { method: "DELETE" }),

  // ── Daily / weekly program ──────────────────────────────
  today: (id: number) => req<DayProgram>(`/users/${id}/daily-program/today`),
  generateToday: (id: number, force = false, train = false) =>
    req<DayProgram>(`/users/${id}/daily-program`, { method: "POST", query: { force, train } }),
  week: (id: number) => req<WeekProgram>(`/users/${id}/weekly-program`),
  generateWeek: (id: number, force = false) =>
    req<WeekProgram>(`/users/${id}/weekly-program`, { method: "POST", query: { force } }),

  // ── Workout logs / history ──────────────────────────────
  logs: (id: number, query?: Query) =>
    req<{ total: number; offset: number; logs: LogSummary[] }>(`/users/${id}/workout-logs`, { query }),
  log: (id: number, logId: number) => req<WorkoutLog>(`/users/${id}/workout-logs/${logId}`),
  completeLog: (id: number, logId: number, body?: { performances: unknown[] }) =>
    req<WorkoutLog>(`/users/${id}/workout-logs/${logId}/complete`, { method: "POST", ...json(body ?? { performances: [] }) }),
  reopenLog: (id: number, logId: number) =>
    req<WorkoutLog>(`/users/${id}/workout-logs/${logId}/reopen`, { method: "POST" }),
  deleteLog: (id: number, logId: number) =>
    req(`/users/${id}/workout-logs/${logId}`, { method: "DELETE" }),

  // ── Custom builder ──────────────────────────────────────
  builderOptions: (id: number) => req<BuilderOptions>(`/users/${id}/workouts/options`),
  workouts: (id: number, query?: Query) => req<WorkoutLog[]>(`/users/${id}/workouts`, { query }),
  workout: (id: number, wId: number) => req<WorkoutLog>(`/users/${id}/workouts/${wId}`),
  createWorkout: (id: number, body: Record<string, unknown>) =>
    req<WorkoutLog>(`/users/${id}/workouts`, { method: "POST", ...json(body) }),
  updateWorkout: (id: number, wId: number, body: Record<string, unknown>) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}`, { method: "PATCH", ...json(body) }),
  deleteWorkout: (id: number, wId: number) =>
    req(`/users/${id}/workouts/${wId}`, { method: "DELETE" }),
  duplicateWorkout: (id: number, wId: number, query?: Query) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/duplicate`, { method: "POST", query }),
  workoutFromLog: (id: number, logId: number, query?: Query) =>
    req<WorkoutLog>(`/users/${id}/workouts/from-log/${logId}`, { method: "POST", query }),
  addExercise: (id: number, wId: number, body: Record<string, unknown>) =>
    req<MutationResponse>(`/users/${id}/workouts/${wId}/exercises`, { method: "POST", ...json(body) }),
  updateExercise: (id: number, wId: number, weId: number, body: Record<string, unknown>) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/exercises/${weId}`, { method: "PATCH", ...json(body) }),
  removeExercise: (id: number, wId: number, weId: number) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/exercises/${weId}`, { method: "DELETE" }),
  reorderExercises: (id: number, wId: number, exerciseIds: number[]) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/exercises/order`, { method: "PUT", ...json({ exercise_ids: exerciseIds }) }),
  suggestions: (id: number, wId: number, query: Query) =>
    req<SuggestionResponse>(`/users/${id}/workouts/${wId}/suggestions`, { query }),
  analysis: (id: number, wId: number) => req<WorkoutAnalysis>(`/users/${id}/workouts/${wId}/analysis`),
  startWorkout: (id: number, wId: number, query?: Query) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/start`, { method: "POST", query }),
  completeWorkout: (id: number, wId: number, body: { performances: unknown[] }) =>
    req<WorkoutLog>(`/users/${id}/workouts/${wId}/complete`, { method: "POST", ...json(body) }),

  // ── Daily metrics ───────────────────────────────────────
  metrics: (id: number, query?: Query) => req<DailyMetric[]>(`/users/${id}/metrics`, { query }),
  putMetric: (id: number, day: string, body: Record<string, unknown>) =>
    req<DailyMetric>(`/users/${id}/metrics/${day}`, { method: "PUT", ...json(body) }),

  // ── Dashboard ───────────────────────────────────────────
  dash: {
    summary: (id: number, query?: Query) => req<DashSummary>(`/users/${id}/dashboard/summary`, { query }),
    muscleActivation: (id: number, query?: Query) =>
      req<MuscleActivation>(`/users/${id}/dashboard/muscle-activation`, { query }),
    muscleMapJson: (id: number, query?: Query) =>
      req<{ totals: Record<string, number>; workouts: number; peak_muscle: string | null }>(
        `/users/${id}/dashboard/muscle-map`, { query: { ...query, format: "json" } }),
    volume: (id: number, query?: Query) => req<VolumeSeries>(`/users/${id}/dashboard/volume`, { query }),
    workouts: (id: number, query?: Query) => req<WorkoutCounts>(`/users/${id}/dashboard/workouts`, { query }),
    consistency: (id: number, query?: Query) => req<Consistency>(`/users/${id}/dashboard/consistency`, { query }),
    balance: (id: number, query?: Query) => req<Balance>(`/users/${id}/dashboard/balance`, { query }),
    patterns: (id: number, query?: Query) => req<Patterns>(`/users/${id}/dashboard/patterns`, { query }),
    rejections: (id: number, query?: Query) => req<Rejections>(`/users/${id}/dashboard/rejections`, { query }),
    substitutions: (id: number, query?: Query) => req<Substitutions>(`/users/${id}/dashboard/substitutions`, { query }),
    metricSeries: (id: number, metric: string, query?: Query) =>
      req<MetricSeries>(`/users/${id}/dashboard/metrics`, { query: { ...query, metric } }),
    injuries: (id: number) => req<InjuryTimeline>(`/users/${id}/dashboard/injuries`),
    personalRecords: (id: number, query?: Query) =>
      req<PersonalRecords>(`/users/${id}/dashboard/personal-records`, { query }),
  },

  muscleMapSvg: (id: number, query?: Query): string =>
    assetUrl(`/users/${id}/dashboard/muscle-map`, { ...query, format: "svg" }),

  /** Anatomical map rendered from an arbitrary exercise list (a planned or
   *  in-progress workout) — plain activation×sets arithmetic, no history. */
  muscleMapPreview: async (
    id: number,
    items: { exercise_id: string; sets: number }[],
    query?: Query,
  ): Promise<string> => {
    const res = await fetch(`${API_BASE}/users/${id}/dashboard/muscle-map/preview${qs(query)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    if (!res.ok) throw new ApiError(res.status, "Couldn't build the muscle map");
    return res.text();
  },
};

export type Api = typeof api;
export type { Exercise, WorkoutLog };
