import type { WorkoutExercise, SgState } from "./types";

export const titleCase = (s: string) =>
  s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }) {
  return new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString(undefined, opts);
}

export function fmtDayName(iso: string) {
  const d = new Date(iso + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short" });
}

export function relTime(iso: string) {
  const then = new Date(iso).getTime();
  const days = Math.round((Date.now() - then) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.round(days / 7)}w ago`;
  return `${Math.round(days / 30)}mo ago`;
}

/** "3 × 8-12" or "3 × 45s" or "3 × 10-12 @ 40kg" */
export function prescription(ex: Pick<WorkoutExercise, "sets" | "reps" | "duration_seconds" | "weight_kg">) {
  const target = ex.reps
    ? ex.reps
    : ex.duration_seconds
      ? ex.duration_seconds >= 60
        ? `${Math.round(ex.duration_seconds / 60)} min`
        : `${ex.duration_seconds}s`
      : "—";
  const base = `${ex.sets} × ${target}`;
  return ex.weight_kg ? `${base} · ${ex.weight_kg}kg` : base;
}

export const todayISO = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local

export function isoDaysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toLocaleDateString("en-CA");
}

export const SG_META: Record<SgState, { label: string; short: string; token: string }> = {
  eligible: { label: "Good to go", short: "Eligible", token: "good" },
  preference_penalized: { label: "You've pushed back on this", short: "Deprioritised", token: "pref" },
  cooldown: { label: "On cooldown", short: "Cooldown", token: "warn" },
  suppressed: { label: "Not right now — injury", short: "Blocked", token: "bad" },
};

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
export const compact = (n: number | null | undefined) =>
  n == null ? "—" : Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(n);
