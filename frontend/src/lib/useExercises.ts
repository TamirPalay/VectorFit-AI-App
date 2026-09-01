import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Exercise } from "./types";

/**
 * Loads the whole exercise catalogue once and exposes an id→Exercise map.
 * Used to show descriptions / muscle data next to a workout's exercises
 * (the workout endpoints only carry the name).
 */
export function useExerciseMap() {
  const q = useQuery({
    queryKey: ["exercise-catalogue"],
    queryFn: async () => {
      const acc: Exercise[] = [];
      for (let offset = 0; ; offset += 200) {
        const page = await api.exercises({ limit: 200, offset });
        acc.push(...page.exercises);
        if (acc.length >= page.total || page.exercises.length === 0) break;
      }
      return acc;
    },
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const map = new Map<string, Exercise>();
  for (const ex of q.data ?? []) map.set(ex.id, ex);
  return { map, isLoading: q.isLoading };
}

export const isCompound = (ex: Exercise) =>
  Object.values(ex.muscle_activation).filter((v) => v >= 0.5).length >= 3;

export function topMuscles(ex: Exercise, n = 3): { muscle: string; value: number }[] {
  return Object.entries(ex.muscle_activation)
    .filter(([, v]) => v > 0.15)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([muscle, value]) => ({ muscle, value }));
}
