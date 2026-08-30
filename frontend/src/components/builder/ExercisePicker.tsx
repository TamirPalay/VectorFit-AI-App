import { useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { SG_META, titleCase } from "../../lib/format";
import { Sheet } from "../ui/Sheet";
import { Chip, Pill, Spinner, Segmented } from "../ui/primitives";
import { ExerciseDetailSheet } from "../ExerciseDetailSheet";
import { Check, Info, Plus, Search } from "../icons";
import type { Exercise, SgState } from "../../lib/types";
import s from "../../screens/Builder.module.css";

const BODY_PARTS = ["chest", "back", "shoulders", "arms", "core", "quads", "hamstrings", "glutes", "calves"];

interface Row { exercise: Exercise; state?: SgState; mechanic: string; added: boolean }

interface Props {
  userId: number;
  workoutId: number;
  addedIds: Set<string>;
  onAdd: (exerciseId: string) => void;
  adding: string | null;
  onClose: () => void;
}

export function ExercisePicker({ userId, workoutId, addedIds, onAdd, adding, onClose }: Props) {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"suggested" | "all">("suggested");
  const [bodyPart, setBodyPart] = useState<string | null>(null);
  const [mechanic, setMechanic] = useState<"compound" | "isolation" | null>(null);
  const [supportedOnly, setSupportedOnly] = useState(false);
  const [showBlocked, setShowBlocked] = useState(false);
  const [detail, setDetail] = useState<Exercise | null>(null);

  const effectiveMode = q.trim() ? "all" : mode;

  const query = {
    q: q.trim() || undefined,
    body_part: bodyPart ?? undefined,
    mechanic: mechanic ?? undefined,
    force_direction: supportedOnly ? "supported" : undefined,
    facets: true,
    limit: 60,
  };

  const suggested = useQuery({
    queryKey: ["suggestions", userId, workoutId, query, showBlocked],
    queryFn: () => api.suggestions(userId, workoutId, {
      ...query,
      eligibility: showBlocked ? "flag_suppressed" : "eligible_only",
      exclude_added: false,
    }),
    enabled: effectiveMode === "suggested",
    placeholderData: keepPreviousData,
  });

  const all = useQuery({
    queryKey: ["exercises", query, showBlocked],
    queryFn: () => api.exercises(query),
    enabled: effectiveMode === "all",
    placeholderData: keepPreviousData,
  });

  const allIds = (all.data?.exercises ?? []).map((e) => e.id);
  const states = useQuery({
    queryKey: ["sg-batch", userId, allIds],
    queryFn: () => api.suggestibilityBatch(userId, allIds),
    enabled: effectiveMode === "all" && allIds.length > 0,
    placeholderData: keepPreviousData,
  });
  const stateMap = new Map((states.data ?? []).map((r) => [r.exercise_id, r.state as SgState]));

  const loading = suggested.isLoading || all.isLoading;

  const rows: Row[] = useMemo(() => {
    if (effectiveMode === "suggested" && suggested.data) {
      return suggested.data.suggestions.map((x) => ({
        exercise: x.exercise, state: x.suggestibility_state, mechanic: x.mechanic,
        added: addedIds.has(x.exercise.id),
      }));
    }
    if (effectiveMode === "all" && all.data) {
      return all.data.exercises
        .map((e) => ({
          exercise: e,
          state: stateMap.get(e.id),
          mechanic: Object.values(e.muscle_activation).filter((v) => v >= 0.5).length >= 3 ? "compound" : "isolation",
          added: addedIds.has(e.id),
        }))
        .filter((r) => showBlocked || !r.state || (r.state !== "suppressed" && r.state !== "cooldown"));
    }
    return [];
  }, [effectiveMode, suggested.data, all.data, addedIds, showBlocked, stateMap]);

  const facets = (effectiveMode === "suggested" ? suggested.data?.facets : all.data?.facets) ?? {};
  const total = effectiveMode === "suggested" ? suggested.data?.total : all.data?.total;

  return (
    <Sheet open onClose={onClose} title="Add exercises" wide>
      <div className={s.pickerTools}>
        <div className={s.searchBox}>
          <Search className="dim" width="1em" height="1em" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search all 316 exercises…"
            autoFocus
          />
          {q && <button onClick={() => setQ("")} className="dim" aria-label="Clear">✕</button>}
        </div>

        {!q.trim() && (
          <Segmented<"suggested" | "all">
            value={mode}
            onChange={setMode}
            options={[{ value: "suggested", label: "Suggested" }, { value: "all", label: "Browse all" }]}
          />
        )}

        <div className={s.chipRow}>
          <Chip active={mechanic === "compound"} onClick={() => setMechanic(mechanic === "compound" ? null : "compound")}>Compound</Chip>
          <Chip active={mechanic === "isolation"} onClick={() => setMechanic(mechanic === "isolation" ? null : "isolation")}>Isolation</Chip>
          <Chip active={supportedOnly} onClick={() => setSupportedOnly((v) => !v)}>Supported only</Chip>
          <Chip active={showBlocked} onClick={() => setShowBlocked((v) => !v)}>Show injury-blocked</Chip>
        </div>
        <div className={s.chipRow}>
          {BODY_PARTS.map((bp) => (
            <Chip
              key={bp}
              active={bodyPart === bp}
              count={facets.body_part?.[bp]}
              onClick={() => setBodyPart(bodyPart === bp ? null : bp)}
            >
              {titleCase(bp)}
            </Chip>
          ))}
        </div>
      </div>

      {loading && <div style={{ display: "grid", placeItems: "center", padding: 32 }}><Spinner /></div>}

      {!loading && rows.length === 0 && (
        <p className="dim" style={{ textAlign: "center", padding: 24, fontSize: "0.88rem" }}>
          Nothing matches those filters.
        </p>
      )}

      <div>
        {rows.map(({ exercise, state, mechanic: mech, added }) => (
          <div key={exercise.id} className={s.result}>
            <button className={s.rn} style={{ textAlign: "left" }} onClick={() => setDetail(exercise)}>
              <div className={s.rt}>
                {exercise.name}
                {state && state !== "eligible" && (
                  <Pill token={SG_META[state].token as never}>{SG_META[state].short}</Pill>
                )}
                <Info width="0.85em" height="0.85em" style={{ color: "var(--text-faint)" }} />
              </div>
              <div className={s.rs}>
                {titleCase(exercise.movement_pattern)} · {mech} · {exercise.equipment_required.map(titleCase).join(", ")}
              </div>
            </button>
            <button
              className={`${s.addIcon} ${added ? s.in : ""}`}
              disabled={adding === exercise.id}
              onClick={() => onAdd(exercise.id)}
              aria-label={added ? "Add again" : "Add"}
            >
              {adding === exercise.id ? <Spinner /> : added ? <Check width="1em" height="1em" /> : <Plus width="1.1em" height="1.1em" />}
            </button>
          </div>
        ))}
      </div>

      {detail && <ExerciseDetailSheet exercise={detail} userId={userId} onClose={() => setDetail(null)} />}

      {total != null && total > rows.length && (
        <p className="dim" style={{ textAlign: "center", padding: "12px 0 0", fontSize: "0.8rem" }}>
          Showing {rows.length} of {total} — refine with search or filters.
        </p>
      )}
    </Sheet>
  );
}
