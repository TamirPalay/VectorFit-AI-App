import type { WorkoutExercise } from "./types";

const WORK_PER_REP = 3;
const DEFAULT_WORK = 35;

/** Client-side mirror of the backend's session-time estimate (minutes). */
export function estimateMinutes(exs: Pick<WorkoutExercise, "sets" | "reps" | "duration_seconds" | "rest_seconds">[]): number {
  const secs = exs.reduce((total, e) => {
    let work: number;
    if (e.duration_seconds) work = e.duration_seconds;
    else if (e.reps) {
      const m = e.reps.match(/\d+/);
      work = m ? Number(m[0]) * WORK_PER_REP : DEFAULT_WORK;
    } else work = DEFAULT_WORK;
    return total + e.sets * (work + (e.rest_seconds || 0));
  }, 0);
  return Math.round(secs / 60);
}
