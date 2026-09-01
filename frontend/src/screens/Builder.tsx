import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { prescription, titleCase } from "../lib/format";
import { useExerciseMap } from "../lib/useExercises";
import { Button, Card, SectionTitle, Loader, ErrorState, IconButton, Bar, Pill } from "../components/ui/primitives";
import { Sheet } from "../components/ui/Sheet";
import { useToast } from "../components/ui/Toast";
import { ExercisePicker } from "../components/builder/ExercisePicker";
import { ExerciseDetailSheet } from "../components/ExerciseDetailSheet";
import { MuscleMapPreview } from "../components/MuscleMapPreview";
import { AiNote } from "../components/ui/AiNote";
import { ArrowDown, ArrowUp, Check, ChevronLeft, Edit, Minus, Play, Plus, Trash } from "../components/icons";
import type { Exercise, WorkoutExercise } from "../lib/types";
import s from "./Builder.module.css";

export function Builder() {
  const { workoutId } = useParams();
  return workoutId ? <BuilderEdit workoutId={Number(workoutId)} /> : <BuilderNew />;
}

// ── Step 1: name + type ──────────────────────────────────
function BuilderNew() {
  const { userId } = useUser();
  const id = userId as number;
  const nav = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [type, setType] = useState("full_body");
  const opts = useQuery({ queryKey: ["builderOptions", id], queryFn: () => api.builderOptions(id) });

  const create = useMutation({
    mutationFn: () => api.createWorkout(id, { name: name.trim(), workout_type: type, is_template: true }),
    onSuccess: (w) => nav(`/plan/build/${w.id}`, { replace: true }),
    onError: (e: Error) => toast(e.message, "err"),
  });
  const focusOptions = opts.data?.focus_options ?? [{ value: "full_body", label: "Full Body" }];

  return (
    <div className="screen">
      <button className="row gap-1 dim" onClick={() => nav("/plan")} style={{ fontSize: "0.85rem" }}>
        <ChevronLeft width="1em" height="1em" /> Plan
      </button>
      <div className="screen-head"><h1>New workout</h1><p>Name it and pick a focus.</p></div>

      <Card className="stack gap-4">
        <input
          className={s.nameInput}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Monday Pull"
          autoFocus
        />
        <div className="stack gap-2">
          <span className="eyebrow">Focus</span>
          <div className="row gap-2 wrap">
            {focusOptions.map((f) => (
              <button key={f.value} className={`vf-chip ${type === f.value ? "on" : ""}`} onClick={() => setType(f.value)}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <Button size="lg" block disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
          Start building
        </Button>
      </Card>
    </div>
  );
}

// ── Step 2: build ────────────────────────────────────────
function BuilderEdit({ workoutId }: { workoutId: number }) {
  const { userId } = useUser();
  const id = userId as number;
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();

  const wQ = useQuery({ queryKey: ["workout", id, workoutId], queryFn: () => api.workout(id, workoutId) });
  const aQ = useQuery({ queryKey: ["analysis", id, workoutId], queryFn: () => api.analysis(id, workoutId), enabled: !!wQ.data?.exercises.length });
  const optsQ = useQuery({ queryKey: ["builderOptions", id], queryFn: () => api.builderOptions(id) });

  const [picking, setPicking] = useState(false);
  const [pickMuscle, setPickMuscle] = useState<string | null>(null);
  const [editing, setEditing] = useState<WorkoutExercise | null>(null);
  const [addingId, setAddingId] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const [detail, setDetail] = useState<Exercise | null>(null);
  const { map: exMap } = useExerciseMap();

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["workout", id, workoutId] });
    qc.invalidateQueries({ queryKey: ["analysis", id, workoutId] });
    qc.invalidateQueries({ queryKey: ["workouts", id] });
  };

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateWorkout(id, workoutId, body),
    onSuccess: (w) => qc.setQueryData(["workout", id, workoutId], w),
  });
  const add = useMutation({
    mutationFn: (exerciseId: string) => api.addExercise(id, workoutId, { exercise_id: exerciseId, sets: 3, reps: "8-12" }),
    onMutate: (exId) => setAddingId(exId),
    onSettled: () => setAddingId(null),
    onSuccess: (res) => {
      qc.setQueryData(["workout", id, workoutId], res.workout);
      qc.invalidateQueries({ queryKey: ["analysis", id, workoutId] });
      res.warnings.forEach((w) => toast(w, "info"));
    },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const editEx = useMutation({
    mutationFn: ({ weId, body }: { weId: number; body: Record<string, unknown> }) =>
      api.updateExercise(id, workoutId, weId, body),
    onSuccess: (w) => { qc.setQueryData(["workout", id, workoutId], w); invalidate(); setEditing(null); },
  });
  const removeEx = useMutation({
    mutationFn: (weId: number) => api.removeExercise(id, workoutId, weId),
    onSuccess: (w) => { qc.setQueryData(["workout", id, workoutId], w); invalidate(); },
  });
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.reorderExercises(id, workoutId, ids),
    onSuccess: (w) => qc.setQueryData(["workout", id, workoutId], w),
  });
  const start = useMutation({
    mutationFn: () => api.startWorkout(id, workoutId),
    onSuccess: (log) => { qc.invalidateQueries({ queryKey: ["logs", id] }); nav(`/progress/workout/${log.id}`); },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const del = useMutation({
    mutationFn: () => api.deleteWorkout(id, workoutId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workouts", id] }); nav("/plan"); },
  });

  if (wQ.isLoading) return <Loader label="Loading workout…" />;
  if (wQ.isError || !wQ.data) return <ErrorState error={wQ.error} retry={() => wQ.refetch()} />;

  const w = wQ.data;
  const exs = [...w.exercises].sort((a, b) => a.position - b.position);
  const addedIds = new Set(exs.map((e) => e.exercise_id));

  const move = (idx: number, dir: -1 | 1) => {
    const ids = exs.map((e) => e.id);
    const j = idx + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    reorder.mutate(ids);
  };

  return (
    <div className="screen">
      <button className="row gap-1 dim" onClick={() => nav("/plan")} style={{ fontSize: "0.85rem" }}>
        <ChevronLeft width="1em" height="1em" /> Plan
      </button>

      <div className={s.head}>
        <input
          key={w.id}
          ref={nameRef}
          className={s.nameInput}
          defaultValue={w.name ?? ""}
          onBlur={() => {
            const v = nameRef.current?.value.trim() ?? "";
            if (v && v !== w.name) patch.mutate({ name: v });
          }}
          placeholder="Workout name"
        />
        <div className="row gap-2 wrap">
          {(optsQ.data?.focus_options ?? []).map((f) => (
            <button key={f.value} className={`vf-chip ${w.workout_type === f.value ? "on" : ""}`}
              onClick={() => patch.mutate({ workout_type: f.value })}>
              {f.label}
            </button>
          ))}
        </div>
        <textarea
          key={`notes-${w.id}`}
          ref={notesRef}
          className="vf-textarea"
          defaultValue={w.notes ?? ""}
          placeholder="Notes — how it should feel, when to do it, tweaks…"
          style={{ minHeight: 48 }}
          onBlur={() => {
            const v = notesRef.current?.value.trim() ?? "";
            if (v !== (w.notes ?? "")) patch.mutate({ notes: v || null });
          }}
        />
        <label className="row gap-2" style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>
          <input type="checkbox" checked={w.is_template} onChange={(e) => patch.mutate({ is_template: e.target.checked })} />
          Keep in "Your workouts" (reusable)
        </label>
      </div>

      {/* Exercises */}
      <Card variant="flush">
        {exs.length === 0 && (
          <p className="dim" style={{ textAlign: "center", padding: 24, fontSize: "0.88rem" }}>
            No exercises yet — add your first below.
          </p>
        )}
        {exs.map((ex, i) => (
          <div key={ex.id} className={s.exRow}>
            <div className={s.reorder}>
              <button disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp width="0.85em" height="0.85em" /></button>
              <button disabled={i === exs.length - 1} onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown width="0.85em" height="0.85em" /></button>
            </div>
            <button className={s.info} style={{ textAlign: "left" }}
              onClick={() => { const e = exMap.get(ex.exercise_id); if (e) setDetail(e); }}>
              <div className="n">
                {ex.substituted_for_name && <span style={{ textDecoration: "line-through", color: "var(--text-faint)", fontWeight: 500 }}>{ex.substituted_for_name} → </span>}
                {ex.exercise_name}
              </div>
              <div className="p">{prescription(ex)} · rest {ex.rest_seconds}s</div>
              {ex.notes && <div className="note">{ex.notes}</div>}
              {exMap.get(ex.exercise_id)?.description && (
                <div className="note" style={{ color: "var(--text-faint)", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {exMap.get(ex.exercise_id)!.description}
                </div>
              )}
            </button>
            <div className={s.rowActs}>
              <IconButton onClick={() => setEditing(ex)} aria-label="Edit"><Edit width="1em" height="1em" /></IconButton>
              <IconButton onClick={() => removeEx.mutate(ex.id)} aria-label="Remove"><Trash width="1em" height="1em" /></IconButton>
            </div>
          </div>
        ))}
      </Card>

      <button className={s.addBtn} onClick={() => { setPickMuscle(null); setPicking(true); }}>
        <Plus width="1.1em" height="1.1em" /> Add exercise
      </button>

      {/* Muscle map — tap a region to filter the picker */}
      <Card>
        <SectionTitle extra="tap to filter">Muscle map</SectionTitle>
        <div style={{ marginTop: 10 }}>
          <MuscleMapPreview
            userId={id}
            items={exs.map((e) => ({ exercise_id: e.exercise_id, sets: e.sets }))}
            showToggle
            activeMuscle={pickMuscle}
            onMuscleClick={(m) => { setPickMuscle(m); setPicking(true); }}
          />
        </div>
      </Card>

      {/* Analysis */}
      {exs.length > 0 && aQ.data && (
        <Card>
          <SectionTitle extra={`~${aQ.data.estimated_minutes} min`}>Workout check</SectionTitle>
          <div style={{ marginTop: 10 }}>
            <AiNote kind="engine" plain details={
              <>
                Muscle coverage and estimated minutes are pure arithmetic on the exercise labels.
                The injury / cooldown conflicts below come from the <b>suggestibility engine</b> checking
                every pick against your active injuries and recent rejections — the same engine that
                auto-swaps exercises in your daily program. Nothing here is blocked; it's advice.
              </>
            }>
              This check is run by the engine, not the AI coach — it never changes your picks, just flags them.
            </AiNote>
          </div>
          <div className={s.analysis} style={{ marginTop: 12 }}>
            <div className={s.verdictRow}>
              <Pill token={verdictToken(aQ.data.duration_verdict)}>{verdictLabel(aQ.data.duration_verdict, aQ.data.estimated_minutes, aQ.data.target_minutes)}</Pill>
              {Object.entries(aQ.data.pattern_breakdown).map(([p, c]) => (
                <span key={p} className="dim mono" style={{ fontSize: "0.76rem" }}>{titleCase(p)} {c}</span>
              ))}
            </div>

            {aQ.data.injury_conflicts.length > 0 && (
              <div className={s.confList}>
                {aQ.data.injury_conflicts.map((c, i) => <div key={i} className={s.conf}>⚠︎ {c}</div>)}
              </div>
            )}
            {aQ.data.warnings.filter((wn) => !wn.startsWith("Injury")).map((wn, i) => (
              <div key={i} className={s.warnItem}>{wn}</div>
            ))}

            <div>
              <span className="eyebrow">Muscle coverage</span>
              <div className={s.covGrid} style={{ marginTop: 6 }}>
                {aQ.data.muscle_coverage.slice(0, 6).map((m) => (
                  <div key={m.muscle} className={s.covRow}>
                    <span className={s.cl}>{m.display_name}</span>
                    <Bar value={m.activation} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      <p className="dim" style={{ fontSize: "0.78rem", textAlign: "center" }}>
        Changes save automatically.
      </p>
      <div className="row gap-3">
        <Button variant="danger" onClick={() => confirm("Delete this workout?") && del.mutate()} aria-label="Delete workout">
          <Trash width="1em" height="1em" />
        </Button>
        <Button className="grow" onClick={() => nav("/plan")}>
          <Check width="1em" height="1em" /> Save &amp; close
        </Button>
        <Button variant="secondary" className="grow" disabled={!exs.length} loading={start.isPending} onClick={() => start.mutate()}>
          <Play width="1em" height="1em" /> Start now
        </Button>
      </div>

      {picking && (
        <ExercisePicker
          userId={id}
          workoutId={workoutId}
          addedIds={addedIds}
          adding={addingId}
          initialMuscle={pickMuscle}
          onAdd={(exId) => add.mutate(exId)}
          onClose={() => { setPicking(false); setPickMuscle(null); }}
        />
      )}
      {detail && <ExerciseDetailSheet exercise={detail} userId={id} onClose={() => setDetail(null)} />}
      {editing && (
        <ExerciseEditor
          ex={editing}
          onClose={() => setEditing(null)}
          onSave={(body) => editEx.mutate({ weId: editing.id, body })}
          saving={editEx.isPending}
        />
      )}
    </div>
  );
}

// ── Exercise editor sheet ────────────────────────────────
function ExerciseEditor({
  ex, onClose, onSave, saving,
}: {
  ex: WorkoutExercise;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const [sets, setSets] = useState(ex.sets);
  const [mode, setMode] = useState<"reps" | "time">(ex.duration_seconds ? "time" : "reps");
  const [reps, setReps] = useState(ex.reps ?? "8-12");
  const [dur, setDur] = useState(ex.duration_seconds ?? 45);
  const [rest, setRest] = useState(ex.rest_seconds);
  const [weight, setWeight] = useState(ex.weight_kg ?? 0);
  const [notes, setNotes] = useState(ex.notes ?? "");

  const save = () =>
    onSave({
      sets,
      reps: mode === "reps" ? reps : null,
      duration_seconds: mode === "time" ? dur : null,
      rest_seconds: rest,
      weight_kg: weight > 0 ? weight : null,
      notes: notes.trim() || null,
    });

  return (
    <Sheet
      open
      onClose={onClose}
      title={ex.exercise_name}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={saving} onClick={save}>Save</Button></>}
    >
      <div className="stack gap-4">
        <div className={s.editGrid}>
          <div className={s.field}>
            <span>Sets</span>
            <div className={s.stepper}>
              <button onClick={() => setSets((v) => Math.max(1, v - 1))}><Minus width="0.9em" height="0.9em" /></button>
              <span className="v">{sets}</span>
              <button onClick={() => setSets((v) => Math.min(20, v + 1))}><Plus width="0.9em" height="0.9em" /></button>
            </div>
          </div>
          <div className={s.field}>
            <span>Rest (s)</span>
            <div className={s.stepper}>
              <button onClick={() => setRest((v) => Math.max(0, v - 15))}><Minus width="0.9em" height="0.9em" /></button>
              <span className="v">{rest}</span>
              <button onClick={() => setRest((v) => v + 15)}><Plus width="0.9em" height="0.9em" /></button>
            </div>
          </div>
        </div>

        <div className={s.field}>
          <span>Target</span>
          <div className="row gap-2">
            <button className={`vf-chip ${mode === "reps" ? "on" : ""}`} onClick={() => setMode("reps")}>Reps</button>
            <button className={`vf-chip ${mode === "time" ? "on" : ""}`} onClick={() => setMode("time")}>Time</button>
          </div>
          {mode === "reps" ? (
            <input className="vf-input" value={reps} onChange={(e) => setReps(e.target.value)} placeholder="8-12 or AMRAP" style={{ marginTop: 6 }} />
          ) : (
            <input type="number" className="vf-input" value={dur} min={5} step={5}
              onChange={(e) => setDur(Math.max(5, +e.target.value || 45))} style={{ marginTop: 6 }} />
          )}
        </div>

        <div className={s.field}>
          <span>Weight (kg) — optional</span>
          <input type="number" className="vf-input" value={weight || ""} min={0} step={2.5}
            onChange={(e) => setWeight(Math.max(0, +e.target.value || 0))} placeholder="—" />
        </div>

        <div className={s.field}>
          <span>Notes</span>
          <textarea className="vf-textarea" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Pause at the bottom, etc." />
        </div>
      </div>
    </Sheet>
  );
}

const verdictToken = (v: string) => (v === "on_target" ? "good" : v === "unknown" ? "plain" : "warn") as never;
const verdictLabel = (v: string, est: number, target: number | null) => {
  if (v === "on_target") return `On target (~${est} min)`;
  if (v === "short") return `Light — ~${est} vs ${target} min`;
  if (v === "long") return `Long — ~${est} vs ${target} min`;
  return `~${est} min`;
};
