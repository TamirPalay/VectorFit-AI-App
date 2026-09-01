import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { titleCase, SG_META, pct } from "../lib/format";
import { Sheet } from "./ui/Sheet";
import { Pill, Bar, Spinner } from "./ui/primitives";
import { AiBadge } from "./ui/AiNote";
import { MUSCLE_LABEL } from "../lib/muscleLabels";
import type { Exercise, SgState } from "../lib/types";

export function ExerciseDetailSheet({
  exercise, userId, onClose,
}: {
  exercise: Exercise;
  userId?: number;
  onClose: () => void;
}) {
  // Fast, no-LLM state check first — this is what decides whether we even need
  // to reach for alternatives.
  const stateQ = useQuery({
    queryKey: ["sg-state", userId, exercise.id],
    queryFn: () => api.suggestibilityBatch(userId as number, [exercise.id]),
    enabled: !!userId,
    retry: 0,
  });
  const state = stateQ.data?.[0]?.state as SgState | undefined;
  const reason = stateQ.data?.[0]?.suppression_reason;
  const blocked = state === "suppressed" || state === "cooldown";

  // Only look for alternatives when the exercise is actually blocked. Uses the
  // fast no-LLM substitute endpoint (~0.3s) rather than /explain (LLM, ~40s).
  const subsQ = useQuery({
    queryKey: ["sg-subs", userId, exercise.id],
    queryFn: () => api.substitutes(userId as number, exercise.id, 3),
    enabled: !!userId && blocked,
    retry: 0,
  });

  const top = Object.entries(exercise.muscle_activation)
    .filter(([, v]) => v >= 0.15)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7);
  const compound = Object.values(exercise.muscle_activation).filter((v) => v >= 0.5).length >= 3;

  return (
    <Sheet open onClose={onClose} title={exercise.name}>
      <div className="stack gap-4">
        <div className="row gap-2 wrap">
          <Pill token="plain">{titleCase(exercise.movement_pattern)}</Pill>
          <Pill token="plain">{compound ? "Compound" : "Isolation"}</Pill>
          <Pill token="plain">{titleCase(exercise.force_direction)}</Pill>
        </div>

        <p style={{ fontSize: "0.9rem", lineHeight: 1.6, color: "var(--text-dim)" }}>
          {exercise.description}
        </p>

        <div className="stack gap-2">
          <span className="eyebrow">Muscles worked</span>
          <div className="stack gap-2" style={{ marginTop: 2 }}>
            {top.map(([mm, v]) => (
              <div key={mm} style={{ display: "grid", gridTemplateColumns: "96px 1fr 34px", gap: 10, alignItems: "center", fontSize: "0.82rem" }}>
                <span className="dim">{MUSCLE_LABEL[mm] ?? titleCase(mm)}</span>
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

        {/* ── Fit for you ── */}
        {userId && (
          <div className="stack gap-2">
            <span className="eyebrow">Fit for you <AiBadge kind="engine" title="Checked by the suggestibility engine against your injuries and past feedback" /></span>

            {stateQ.isLoading && <div className="row gap-2 dim"><Spinner /> checking against your profile…</div>}

            {stateQ.isError && (
              <p className="dim" style={{ fontSize: "0.85rem" }}>Couldn't check right now — try again in a moment.</p>
            )}

            {state && (
              <FitLine state={state} reason={reason} />
            )}

            {blocked && (
              <>
                {subsQ.isLoading && <div className="row gap-2 dim"><Spinner /> finding safer alternatives…</div>}
                {subsQ.isError && (
                  <p className="dim" style={{ fontSize: "0.85rem" }}>Couldn't load alternatives right now.</p>
                )}
                {subsQ.data && subsQ.data.length > 0 && (
                  <div className="stack gap-2">
                    <span className="dim" style={{ fontSize: "0.82rem" }}>Closest moves you can do instead:</span>
                    {subsQ.data.map((sub) => (
                      <div key={sub.exercise.id} style={{ padding: "10px 12px", background: "var(--good-wash)", borderRadius: 10 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{sub.exercise.name}</div>
                        <div className="mono dim" style={{ fontSize: "0.74rem", marginTop: 3 }}>
                          {Math.round(sub.similarity * 100)}% match · covers {Math.round(sub.coverage * 100)}% of the muscle work
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {subsQ.data && subsQ.data.length === 0 && (
                  <p className="dim" style={{ fontSize: "0.85rem" }}>
                    No close alternative found — the injury restrictions may block similar moves too.
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Sheet>
  );
}

function FitLine({ state, reason }: { state: SgState; reason?: string | null }) {
  if (state === "eligible") {
    return (
      <p style={{ fontSize: "0.86rem", color: "var(--good)" }}>
        ✓ Good fit — no injury or preference conflict for you.
      </p>
    );
  }
  if (state === "preference_penalized") {
    return (
      <p style={{ fontSize: "0.86rem", color: "var(--warn)" }}>
        You've pushed back on this before, so it's deprioritised — still allowed if you want it.
      </p>
    );
  }
  const meta = SG_META[state];
  return (
    <div className="row gap-2 center" style={{ flexWrap: "wrap" }}>
      <Pill token={meta.token as never} dot>{meta.label}</Pill>
      {reason && <span className="dim" style={{ fontSize: "0.82rem" }}>{titleCase(reason)}</span>}
    </div>
  );
}
export type { Exercise };
