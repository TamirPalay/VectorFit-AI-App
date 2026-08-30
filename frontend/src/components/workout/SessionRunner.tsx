import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { estimateMinutes } from "../../lib/workout";
import { fmtDate } from "../../lib/format";
import { useExerciseMap } from "../../lib/useExercises";
import { Button, Card } from "../ui/primitives";
import { Sheet } from "../ui/Sheet";
import { useToast } from "../ui/Toast";
import { ExerciseItem, type FB } from "./ExerciseItem";
import { ReasonPicker } from "./ReasonPicker";
import { ExerciseDetailSheet } from "../ExerciseDetailSheet";
import { Check, RotateCcw, Bookmark } from "../icons";
import type { Exercise, WorkoutExercise, WorkoutLog } from "../../lib/types";
import s from "./SessionRunner.module.css";

interface Fb { kind: FB; reason?: string }

export function SessionRunner({
  log, userId, onChange, warnings = [], allowSave = true,
}: {
  log: WorkoutLog;
  userId: number;
  onChange?: (updated: WorkoutLog) => void;
  warnings?: string[];
  allowSave?: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { map: exMap } = useExerciseMap();
  const [done, setDone] = useState<Set<number>>(new Set());
  const [fb, setFb] = useState<Record<number, Fb>>(() =>
    Object.fromEntries(log.exercises.filter((e) => e.feedback).map((e) => [e.id, { kind: e.feedback as FB }])),
  );
  const [reasonFor, setReasonFor] = useState<WorkoutExercise | null>(null);
  const [detail, setDetail] = useState<Exercise | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [saving, setSaving] = useState(false);

  const completed = !!log.completed_at;
  const minutes = useMemo(() => estimateMinutes(log.exercises), [log.exercises]);
  const swaps = log.exercises.filter((e) => e.substituted_for_id).length;

  const active = log.exercises.filter((e) => fb[e.id]?.kind !== "rejected");
  const progress = completed ? 1 : active.length ? active.filter((e) => done.has(e.id)).length / active.length : 0;

  const bump = () => {
    ["dash", "logs", "today", "week", "workouts", "rejections"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k, userId] }));
    qc.invalidateQueries({ queryKey: ["dash"] });
  };

  const performances = () =>
    Object.entries(fb)
      .filter(([, v]) => v.kind)
      .map(([weId, v]) => ({ workout_exercise_id: Number(weId), feedback: v.kind, rejection_reason: v.reason }));

  const complete = useMutation({
    mutationFn: () => api.completeLog(userId, log.id, { performances: performances() }),
    onSuccess: (updated) => { onChange?.(updated); bump(); setFinishing(false); toast("Workout logged 💪"); },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const reopen = useMutation({
    mutationFn: () => api.reopenLog(userId, log.id),
    onSuccess: (updated) => { onChange?.(updated); bump(); setDone(new Set()); },
  });
  const save = useMutation({
    mutationFn: (body: { name: string; notes: string }) =>
      api.workoutFromLog(userId, log.id, { name: body.name, as_template: true }).then((w) =>
        body.notes ? api.updateWorkout(userId, w.id, { notes: body.notes }) : w),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workouts", userId] }); setSaving(false); toast("Saved to your workouts"); },
    onError: (e: Error) => toast(e.message, "err"),
  });

  const setFeedback = (we: WorkoutExercise, kind: FB) => {
    if (kind === "rejected") { setReasonFor(we); return; }
    setFb((c) => ({ ...c, [we.id]: { kind } }));
  };
  const toggle = (weId: number) =>
    setDone((cur) => { const n = new Set(cur); n.has(weId) ? n.delete(weId) : n.add(weId); return n; });

  return (
    <>
      <Card variant="flush" className={s.card}>
        {completed && (
          <div className={s.done}><Check /> Completed {fmtDate(log.completed_at!, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div>
        )}
        <div className={s.head}>
          <span className={s.type}>{log.name || log.workout_label || "Workout"}</span>
          <span className={s.meta}>~{minutes}m{swaps ? ` · ${swaps} swapped` : ""}</span>
        </div>
        {!completed && <div className={s.strip}><span style={{ width: `${progress * 100}%` }} /></div>}

        {warnings.map((w, i) => <div key={i} className={s.warn}>⚠︎ {w}</div>)}

        <div>
          {log.exercises.map((ex, i) => (
            <ExerciseItem
              key={ex.id}
              ex={ex}
              index={i}
              description={exMap.get(ex.exercise_id)?.description}
              checked={completed || done.has(ex.id)}
              onToggle={completed ? undefined : () => toggle(ex.id)}
              feedback={fb[ex.id]?.kind ?? null}
              rejectReason={fb[ex.id]?.reason}
              onFeedback={completed ? undefined : (kind) => setFeedback(ex, kind)}
              onOpen={exMap.get(ex.exercise_id) ? () => setDetail(exMap.get(ex.exercise_id)!) : undefined}
            />
          ))}
        </div>

        <div className={s.foot}>
          {completed ? (
            <div className="row gap-2" style={{ width: "100%" }}>
              {allowSave && (
                <Button variant="secondary" onClick={() => setSaving(true)}>
                  <Bookmark width="1em" height="1em" /> Save
                </Button>
              )}
              <Button variant="ghost" className="grow" loading={reopen.isPending} onClick={() => reopen.mutate()}>
                <RotateCcw width="1em" height="1em" /> Reopen
              </Button>
            </div>
          ) : (
            <Button block size="lg" onClick={() => setFinishing(true)}>
              {progress >= 1 ? "Finish workout" : `Finish (${active.filter((e) => done.has(e.id)).length}/${active.length})`}
            </Button>
          )}
        </div>
      </Card>

      {reasonFor && (
        <ReasonPicker
          exerciseName={reasonFor.exercise_name}
          onClose={() => setReasonFor(null)}
          onPick={(reason) => setFb((c) => ({ ...c, [reasonFor.id]: { kind: "rejected", reason } }))}
        />
      )}
      {detail && <ExerciseDetailSheet exercise={detail} userId={userId} onClose={() => setDetail(null)} />}
      {finishing && (
        <ConfirmFinish
          count={active.filter((e) => done.has(e.id)).length}
          total={active.length}
          rejected={Object.values(fb).filter((v) => v.kind === "rejected").length}
          liked={Object.values(fb).filter((v) => v.kind === "liked").length}
          onClose={() => setFinishing(false)}
          onConfirm={() => complete.mutate()}
          loading={complete.isPending}
        />
      )}
      {saving && (
        <SaveSheet
          defaultName={log.name || log.workout_label || "Workout"}
          onClose={() => setSaving(false)}
          onConfirm={(name, notes) => save.mutate({ name, notes })}
          loading={save.isPending}
        />
      )}
    </>
  );
}

function ConfirmFinish({
  count, total, rejected, liked, onClose, onConfirm, loading,
}: {
  count: number; total: number; rejected: number; liked: number;
  onClose: () => void; onConfirm: () => void; loading: boolean;
}) {
  return (
    <Sheet open onClose={onClose} title="Log this workout?"
      footer={<><Button variant="ghost" onClick={onClose}>Not yet</Button><Button loading={loading} onClick={onConfirm}>Log it</Button></>}>
      <div className="stack gap-3" style={{ fontSize: "0.92rem" }}>
        <p><strong>{count} of {total}</strong> exercises done.</p>
        {liked > 0 && <p className="dim">👍 {liked} liked — we'll keep suggesting those.</p>}
        {rejected > 0 && <p className="dim">✕ {rejected} won't be suggested again.</p>}
        <p className="dim" style={{ fontSize: "0.85rem" }}>Your feedback tunes future workouts. You can reopen this anytime.</p>
      </div>
    </Sheet>
  );
}

function SaveSheet({
  defaultName, onClose, onConfirm, loading,
}: {
  defaultName: string;
  onClose: () => void;
  onConfirm: (name: string, notes: string) => void;
  loading: boolean;
}) {
  const [name, setName] = useState(defaultName);
  const [notes, setNotes] = useState("");
  return (
    <Sheet open onClose={onClose} title="Save to your workouts"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button disabled={!name.trim()} loading={loading} onClick={() => onConfirm(name.trim(), notes.trim())}>Save</Button></>}>
      <div className="stack gap-4">
        <label className="stack gap-1"><span className="eyebrow">Name</span>
          <input className="vf-input" value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
        <label className="stack gap-1"><span className="eyebrow">Notes — why you liked it, tweaks for next time</span>
          <textarea className="vf-textarea" value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Felt great, maybe add a set to the rows…" /></label>
        <p className="dim" style={{ fontSize: "0.82rem" }}>Saved as a reusable template you can start or schedule anytime.</p>
      </div>
    </Sheet>
  );
}
