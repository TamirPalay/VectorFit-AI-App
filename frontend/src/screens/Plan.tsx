import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { fmtDate, fmtDayName, todayISO } from "../lib/format";
import { Button, Card, SectionTitle, Loader, ErrorState, IconButton, EmptyState } from "../components/ui/primitives";
import { Sheet } from "../components/ui/Sheet";
import { useToast } from "../components/ui/Toast";
import { CalendarIcon, Check, ChevronRight, Copy, DumbbellIcon, Edit, Play, Plus, Sparkles, Trash } from "../components/icons";
import { AiNote } from "../components/ui/AiNote";
import type { WorkoutLog } from "../lib/types";
import s from "./Plan.module.css";

export function Plan() {
  const { userId } = useUser();
  const id = userId as number;
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();

  const weekQ = useQuery({ queryKey: ["week", id], queryFn: () => api.week(id) });
  const workoutsQ = useQuery({ queryKey: ["workouts", id], queryFn: () => api.workouts(id) });
  const [scheduling, setScheduling] = useState<WorkoutLog | null>(null);

  const planWeek = useMutation({
    mutationFn: () => api.generateWeek(id, true),
    onSuccess: (w) => { qc.setQueryData(["week", id], w); qc.invalidateQueries({ queryKey: ["today", id] }); toast("Week planned"); },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const del = useMutation({
    mutationFn: (wId: number) => api.deleteWorkout(id, wId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workouts", id] }); toast("Deleted"); },
  });
  const dup = useMutation({
    mutationFn: (wId: number) => api.duplicateWorkout(id, wId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workouts", id] }); toast("Duplicated"); },
  });
  const start = useMutation({
    mutationFn: (wId: number) => api.startWorkout(id, wId),
    onSuccess: (log) => { qc.invalidateQueries({ queryKey: ["logs", id] }); nav(`/progress/workout/${log.id}`); },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const schedule = useMutation({
    mutationFn: ({ wId, on }: { wId: number; on: string }) => api.startWorkout(id, wId, { on }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["week", id] });
      qc.invalidateQueries({ queryKey: ["logs", id] });
      setScheduling(null);
      toast("Added to your week");
    },
    onError: (e: Error) => toast(e.message, "err"),
  });

  const days = weekQ.data?.days ?? [];
  const hasPlan = days.some((d) => d.workout);
  const mine = (workoutsQ.data ?? []).filter((w) => !w.completed_at); // templates + drafts
  const templates = mine.filter((w) => w.is_template);
  const drafts = mine.filter((w) => !w.is_template);

  return (
    <div className="screen">
      <div className="screen-head">
        <h1>Plan</h1>
        <p>Your week, and the workouts you've built.</p>
      </div>

      {/* ── Week strip ── */}
      <Card>
        <div className="row spread center" style={{ marginBottom: 12 }}>
          <SectionTitle>This week</SectionTitle>
          {hasPlan && (
            <Button size="sm" variant="ghost" loading={planWeek.isPending} onClick={() => planWeek.mutate()}>
              Re-plan
            </Button>
          )}
        </div>
        {weekQ.isLoading && <Loader />}
        {weekQ.isError && <ErrorState error={weekQ.error} retry={() => weekQ.refetch()} />}
        {weekQ.data && !hasPlan && (
          <EmptyState emoji="📅" title="No week planned yet" action={
            <Button loading={planWeek.isPending} onClick={() => planWeek.mutate()}>
              <Sparkles width="1em" height="1em" /> Plan my week
            </Button>
          }>
            Seven days scheduled around your target, injuries, and recent training.
          </EmptyState>
        )}
        {hasPlan && (
          <>
          <AiNote kind="engine" plain details={
            <>
              Rest days are spaced evenly for your weekly target. Each training day's type is scored
              together with the others so the week reads as one program — two leg-heavy days rarely land
              back to back. Re-plan only rewrites days you haven't done yet.
            </>
          }>
            The week is laid out by the scheduling engine. Workouts you build and schedule sit alongside it.
          </AiNote>
          <div className="hscroll">
            <div className={s.weekStrip}>
              {days.map((d) => {
                const isToday = d.date === todayISO();
                const w = d.workout;
                const dn = !!w?.completed_at;
                return (
                  <div
                    key={d.date}
                    className={`${s.dayCard} ${isToday ? s.today : ""} ${d.is_rest ? s.rest : ""} ${w ? s.tappable : ""}`}
                    onClick={() => w && nav(`/progress/workout/${w.id}`)}
                  >
                    <span className={s.dow}>{fmtDayName(d.date)}</span>
                    <span className={s.label}>{d.is_rest ? "Rest" : w?.workout_label ?? w?.name ?? "—"}</span>
                    <span className={s.sub}>
                      {dn ? <span className={s.doneTick}><Check width="0.9em" height="0.9em" style={{ display: "inline" }} /> done</span>
                        : w ? `${w.exercises.length} exercises` : fmtDate(d.date)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          </>
        )}
      </Card>

      {/* ── Build CTA ── */}
      <button className={s.buildCta} onClick={() => nav("/plan/build")}>
        <span className={s.plus}><Plus /></span>
        <span className="stack" style={{ textAlign: "left" }}>
          <span className={s.t}>Build a workout</span>
          <span className={s.d}>Pick your own exercises — we'll keep them injury-safe.</span>
        </span>
        <ChevronRight className="dim" style={{ marginLeft: "auto" }} />
      </button>

      {/* ── Drafts (unfinished builds) ── */}
      {drafts.length > 0 && (
        <Card variant="flush">
          <div style={{ padding: "14px 14px 0" }}><SectionTitle extra="not saved as a template">Drafts</SectionTitle></div>
          {drafts.map((w) => (
            <div key={w.id} className={s.tpl}>
              <span className={s.icon}><Edit width="1.05em" height="1.05em" /></span>
              <span className={s.meta} onClick={() => nav(`/plan/build/${w.id}`)} style={{ cursor: "pointer" }}>
                <span className="name">{w.name || "Untitled workout"}</span>
                <span className="sub">{w.exercises.length} exercises · {fmtDate(w.started_at)}</span>
              </span>
              <Button size="sm" variant="secondary" onClick={() => nav(`/plan/build/${w.id}`)}>Continue</Button>
            </div>
          ))}
        </Card>
      )}

      {/* ── Saved workouts ── */}
      <Card variant="flush">
        <div style={{ padding: "14px 14px 0" }}>
          <SectionTitle extra={templates.length ? `${templates.length}` : undefined}>Your workouts</SectionTitle>
        </div>
        {workoutsQ.isLoading && <Loader />}
        {workoutsQ.data && templates.length === 0 && (
          <EmptyState emoji="🏋️" title="No saved workouts yet">
            Build one, or save a workout you enjoyed from your history.
          </EmptyState>
        )}
        {templates.map((w) => (
          <TemplateRow
            key={w.id}
            w={w}
            onEdit={() => nav(`/plan/build/${w.id}`)}
            onStart={() => start.mutate(w.id)}
            onSchedule={() => setScheduling(w)}
            onDuplicate={() => dup.mutate(w.id)}
            onDelete={() => { if (confirm(`Delete "${w.name}"?`)) del.mutate(w.id); }}
            starting={start.isPending}
          />
        ))}
      </Card>

      {scheduling && (
        <ScheduleSheet
          workout={scheduling}
          onClose={() => setScheduling(null)}
          onConfirm={(on) => schedule.mutate({ wId: scheduling.id, on })}
          loading={schedule.isPending}
        />
      )}
    </div>
  );
}

function TemplateRow({
  w, onEdit, onStart, onSchedule, onDuplicate, onDelete, starting,
}: {
  w: WorkoutLog;
  onEdit: () => void; onStart: () => void; onSchedule: () => void; onDuplicate: () => void; onDelete: () => void;
  starting: boolean;
}) {
  return (
    <div className={s.tpl}>
      <span className={s.icon}><DumbbellIcon width="1.2em" height="1.2em" /></span>
      <span className={s.meta} onClick={onEdit} style={{ cursor: "pointer" }}>
        <span className="name">{w.name}</span>
        <span className="sub">{w.workout_label ?? "Custom"} · {w.exercises.length} exercises</span>
      </span>
      <span className={s.acts}>
        <IconButton onClick={onSchedule} aria-label="Add to a day"><CalendarIcon width="1em" height="1em" /></IconButton>
        <IconButton onClick={onDuplicate} aria-label="Duplicate"><Copy width="1em" height="1em" /></IconButton>
        <IconButton onClick={onEdit} aria-label="Edit"><Edit width="1em" height="1em" /></IconButton>
        <IconButton onClick={onDelete} aria-label="Delete"><Trash width="1em" height="1em" /></IconButton>
        <Button size="sm" loading={starting} onClick={onStart}><Play width="0.9em" height="0.9em" /> Start</Button>
      </span>
    </div>
  );
}

function ScheduleSheet({
  workout, onClose, onConfirm, loading,
}: {
  workout: WorkoutLog;
  onClose: () => void;
  onConfirm: (on: string) => void;
  loading: boolean;
}) {
  const nextDays = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    return d.toLocaleDateString("en-CA");
  });
  const [pick, setPick] = useState(nextDays[1]);

  return (
    <Sheet open onClose={onClose} title={`Schedule "${workout.name}"`}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button loading={loading} onClick={() => onConfirm(pick)}>Add to {fmtDayName(pick)}</Button></>}>
      <p className="dim" style={{ fontSize: "0.85rem", marginBottom: 12 }}>Pick a day — it'll show up in your week.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(88px, 1fr))", gap: 8 }}>
        {nextDays.map((iso) => (
          <button key={iso} className={`vf-chip ${pick === iso ? "on" : ""}`}
            style={{ justifyContent: "center", padding: "10px 4px", flexDirection: "column", height: "auto" }}
            onClick={() => setPick(iso)}>
            <span style={{ fontWeight: 700 }}>{fmtDayName(iso)}</span>
            <span style={{ fontSize: "0.7rem", opacity: 0.7 }}>{fmtDate(iso)}</span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}
