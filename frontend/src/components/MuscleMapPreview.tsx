import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { scrubMuscleSvg } from "../lib/muscleSvg";
import { MUSCLE_LABEL } from "../lib/muscleLabels";
import { Segmented, Spinner } from "./ui/primitives";
import s from "./MuscleMap.module.css";

type View = "both" | "front" | "back";
export interface MapItem { exercise_id: string; sets: number }

interface Props {
  userId: number;
  items: MapItem[];
  /** when set, tapping a muscle region calls this with the muscle id */
  onMuscleClick?: (muscle: string) => void;
  activeMuscle?: string | null;
  showToggle?: boolean;
}

/**
 * Anatomical muscle map for a *specific* workout (planned or in progress) —
 * projected straight from the exercises' activation labels × set counts. No
 * history, no LLM. Static by default; pass `onMuscleClick` to make each region
 * a filter (used in the builder).
 */
export function MuscleMapPreview({ userId, items, onMuscleClick, activeMuscle, showToggle }: Props) {
  const [view, setView] = useState<View>("both");

  const key = items.map((i) => `${i.exercise_id}:${i.sets}`).join("|");
  const q = useQuery({
    queryKey: ["muscle-map-preview", userId, view, key, activeMuscle],
    staleTime: 60_000,
    enabled: items.length > 0,
    queryFn: async () =>
      scrubMuscleSvg(await api.muscleMapPreview(userId, items, { view, theme: "auto" }), activeMuscle),
  });

  const handleClick = (e: React.MouseEvent) => {
    if (!onMuscleClick) return;
    const el = (e.target as HTMLElement).closest("[data-muscle]");
    const m = el?.getAttribute("data-muscle");
    if (m) onMuscleClick(m);
  };

  if (items.length === 0) {
    return <p className="dim" style={{ fontSize: "0.85rem", padding: "12px 0" }}>Add exercises to see the muscle map.</p>;
  }

  return (
    <div className={s.wrap}>
      {showToggle && (
        <div className={s.toolbar}>
          <Segmented<View>
            value={view}
            onChange={setView}
            options={[
              { value: "both", label: "Both" },
              { value: "front", label: "Front" },
              { value: "back", label: "Back" },
            ]}
          />
        </div>
      )}
      <div className={s.stage}>
        {q.isLoading && <div className={s.loading}><Spinner /></div>}
        {q.isError && <p className="dim" style={{ padding: 24, fontSize: "0.85rem" }}>Muscle map unavailable.</p>}
        {q.data && (
          <div
            className={s.svgHost}
            onClick={handleClick}
            style={onMuscleClick ? { cursor: "pointer" } : undefined}
            dangerouslySetInnerHTML={{ __html: q.data }}
          />
        )}
      </div>
      {onMuscleClick && (
        <p className="dim" style={{ fontSize: "0.76rem", textAlign: "center" }}>
          {activeMuscle
            ? <>Filtering the picker by <b style={{ color: "var(--accent)" }}>{MUSCLE_LABEL[activeMuscle] ?? activeMuscle}</b> — tap the map again to change.</>
            : "Tap a muscle to find exercises that train it."}
        </p>
      )}
    </div>
  );
}
