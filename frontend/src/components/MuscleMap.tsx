import { useQuery } from "@tanstack/react-query";
import { API_BASE } from "../lib/api";
import { scrubMuscleSvg } from "../lib/muscleSvg";
import { MUSCLE_LABEL } from "../lib/muscleLabels";
import { Segmented, Spinner } from "./ui/primitives";
import s from "./MuscleMap.module.css";

type View = "both" | "front" | "back";

interface Props {
  userId: number;
  from?: string;
  to?: string;
  view: View;
  onView: (v: View) => void;
  /** when set, tapping a muscle region calls this with the muscle id */
  onMuscleClick?: (muscle: string) => void;
  activeMuscle?: string | null;
}

/**
 * Fetches the server-rendered anatomical SVG (history-shaded) and inlines it.
 * Pass `onMuscleClick` to make each region a page-wide filter.
 */
export function MuscleMap({ userId, from, to, view, onView, onMuscleClick, activeMuscle }: Props) {
  const q = useQuery({
    queryKey: ["muscle-map-svg", userId, view, from, to, activeMuscle],
    staleTime: 120_000,
    queryFn: async () => {
      const p = new URLSearchParams({ view, format: "svg", theme: "auto" });
      if (from) p.set("date_from", from);
      if (to) p.set("date_to", to);
      const res = await fetch(`${API_BASE}/users/${userId}/dashboard/muscle-map?${p}`);
      if (!res.ok) throw new Error("Couldn't load the muscle map");
      return scrubMuscleSvg(await res.text(), activeMuscle);
    },
  });

  const handleClick = (e: React.MouseEvent) => {
    if (!onMuscleClick) return;
    const m = (e.target as HTMLElement).closest("[data-muscle]")?.getAttribute("data-muscle");
    if (m) onMuscleClick(m);
  };

  return (
    <div className={s.wrap}>
      <div className={s.toolbar}>
        <Segmented<View>
          value={view}
          onChange={onView}
          options={[
            { value: "both", label: "Both" },
            { value: "front", label: "Front" },
            { value: "back", label: "Back" },
          ]}
        />
      </div>
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
        <p className="dim" style={{ fontSize: "0.78rem", textAlign: "center" }}>
          {activeMuscle
            ? <>Filtering everything below by <b style={{ color: "var(--accent)" }}>{MUSCLE_LABEL[activeMuscle] ?? activeMuscle}</b>. Tap it again to clear.</>
            : "Tap a muscle to filter the whole page to workouts that trained it."}
        </p>
      )}
    </div>
  );
}
