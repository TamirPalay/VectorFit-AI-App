import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { titleCase, SG_META, pct } from "../lib/format";
import { Sheet } from "./ui/Sheet";
import { Pill, Bar, Spinner } from "./ui/primitives";
import { MUSCLE_LABEL } from "../lib/muscleLabels";
import type { Exercise, SgState } from "../lib/types";

export function ExerciseDetailSheet({
  exercise, userId, onClose,
}: {
  exercise: Exercise;
  userId?: number;
  onClose: () => void;
}) {
  const sg = useQuery({
    queryKey: ["sg", userId, exercise.id],
    queryFn: () => api.explain(userId as number, exercise.id),
    enabled: !!userId,
    retry: 0,
  });

  const top = Object.entries(exercise.muscle_activation)
    .filter(([, v]) => v >= 0.15)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7);

  const state = sg.data?.suggestibility.state as SgState | undefined;
  const compound = Object.values(exercise.muscle_activation).filter((v) => v >= 0.5).length >= 3;

  return (
    <Sheet open onClose={onClose} title={exercise.name}>
      <div className="stack gap-4">
        <div className="row gap-2 wrap">
          <Pill token="plain">{titleCase(exercise.movement_pattern)}</Pill>
          <Pill token="plain">{compound ? "Compound" : "Isolation"}</Pill>
          <Pill token="plain">{titleCase(exercise.force_direction)}</Pill>
          {state && state !== "eligible" && (
            <Pill token={SG_META[state].token as never} dot>{SG_META[state].label}</Pill>
          )}
        </div>

        <p style={{ fontSize: "0.9rem", lineHeight: 1.6, color: "var(--text-dim)" }}>
          {exercise.description}
        </p>

        <div className="stack gap-2">
          <span className="eyebrow">Muscles worked</span>
          <div className="stack gap-2" style={{ marginTop: 2 }}>
            {top.map(([m, v]) => (
              <div key={m} style={{ display: "grid", gridTemplateColumns: "96px 1fr 34px", gap: 10, alignItems: "center", fontSize: "0.82rem" }}>
                <span className="dim">{MUSCLE_LABEL[m] ?? titleCase(m)}</span>
                <Bar value={v} />
                <span className="mono dim" style={{ fontSize: "0.74rem", textAlign: "right" }}>{pct(v)}</span>
              </div>
            ))}
          </div>
        </div>

        {exercise.equipment_required.length > 0 && (
          <div className="stack gap-1">
            <span className="eyebrow">Equipment</span>
            <span style={{ fontSize: "0.88rem" }}>{exercise.equipment_required.map(titleCase).join(", ")}</span>
          </div>
        )}

        {sg.isLoading && userId && <div className="row gap-2 dim"><Spinner /> checking against your profile…</div>}

        {sg.data && state && state !== "eligible" && sg.data.substitutes.length > 0 && (
          <div className="stack gap-2">
            <span className="eyebrow">Safer alternatives</span>
            {sg.data.substitutes.slice(0, 3).map((sub) => (
              <div key={sub.exercise.id} style={{ padding: "10px 12px", background: "var(--good-wash)", borderRadius: 10 }}>
                <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{sub.exercise.name}</div>
                <div className="dim" style={{ fontSize: "0.8rem", lineHeight: 1.5, marginTop: 2 }}>{sub.explanation}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}
export type { Exercise };
