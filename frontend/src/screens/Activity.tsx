import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { fmtDate, relTime, titleCase } from "../lib/format";
import { reasonLabel } from "../components/workout/ReasonPicker";
import { Card, Loader, ErrorState, EmptyState, Chip, Segmented, IconButton } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ChevronRight, RotateCcw, ThumbsDown, ThumbsUp, X } from "../components/icons";
import type { LogSummary } from "../lib/types";
import s from "./Activity.module.css";

type Tab = "workouts" | "feedback";

export function Activity() {
  const [tab, setTab] = useState<Tab>("workouts");
  return (
    <div className="screen">
      <div className="screen-head"><h1>Activity</h1><p>Everything you've done, liked, and skipped.</p></div>
      <Segmented<Tab>
        value={tab}
        onChange={setTab}
        options={[{ value: "workouts", label: "Workouts" }, { value: "feedback", label: "Preferences" }]}
      />
      {tab === "workouts" ? <Workouts /> : <Preferences />}
    </div>
  );
}

// ── Workouts ─────────────────────────────────────────────
type Status = "all" | "completed" | "planned";
type Source = "" | "daily" | "custom_builder";

function Workouts() {
  const { userId } = useUser();
  const id = userId as number;
  const nav = useNavigate();
  const [status, setStatus] = useState<Status>("all");
  const [source, setSource] = useState<Source>("");

  const q = useQuery({
    queryKey: ["logs", id, status, source],
    queryFn: () => api.logs(id, { status, source: source || undefined, limit: 150 }),
  });

  return (
    <div className="stack gap-3">
      <div className="row gap-2 wrap">
        {(["all", "completed", "planned"] as Status[]).map((v) => (
          <Chip key={v} active={status === v} onClick={() => setStatus(v)}>{titleCase(v)}</Chip>
        ))}
        <span style={{ width: 1, background: "var(--border)", alignSelf: "stretch" }} />
        {([["", "All"], ["daily", "Daily plan"], ["custom_builder", "Custom"]] as [Source, string][]).map(([v, l]) => (
          <Chip key={v} active={source === v} onClick={() => setSource(v)}>{l}</Chip>
        ))}
      </div>

      {q.isLoading && <Loader />}
      {q.isError && <ErrorState error={q.error} retry={() => q.refetch()} />}
      {q.data && q.data.logs.length === 0 && (
        <EmptyState emoji="📭" title="Nothing here yet" action={<Link to="/" style={{ color: "var(--accent)", fontWeight: 600 }}>Start today's workout →</Link>} />
      )}
      {q.data && q.data.logs.length > 0 && (
        <Card variant="flush">
          {q.data.logs.map((l: LogSummary) => (
            <button key={l.id} className={s.logRow} onClick={() => nav(`/progress/workout/${l.id}`)}>
              <span className={s.dot} style={{ background: l.completed ? "var(--good)" : "var(--warn)" }} />
              <span className={s.mid}>
                <span className={s.top}>
                  <span className={s.lbl}>{l.name || l.workout_label || "Workout"}</span>
                  <span className={s.date}>{fmtDate(l.date)} · {relTime(l.date)}</span>
                </span>
                <span className={s.sub}>
                  {l.exercise_count} exercises · {l.total_sets} sets
                  {l.swap_count > 0 && ` · ${l.swap_count} swapped`}
                  {!l.completed && " · planned"}
                </span>
              </span>
              <ChevronRight className={s.chev} />
            </button>
          ))}
        </Card>
      )}
    </div>
  );
}

// ── Preferences (likes / dislikes / rejections) ──────────
function Preferences() {
  const { userId } = useUser();
  const id = userId as number;
  const qc = useQueryClient();
  const toast = useToast();

  const rejQ = useQuery({ queryKey: ["rejections", id], queryFn: () => api.rejections(id) });
  // derive likes/dislikes from completed workout logs
  const logsQ = useQuery({ queryKey: ["logs", id, "completed", "feedback"], queryFn: () => api.logs(id, { status: "completed", limit: 200 }) });

  const detailQ = useQuery({
    queryKey: ["logs-feedback-detail", id],
    queryFn: async () => {
      const ids = (logsQ.data?.logs ?? []).slice(0, 40).map((l) => l.id);
      const logs = await Promise.all(ids.map((lid) => api.log(id, lid)));
      return logs;
    },
    enabled: !!logsQ.data,
  });

  const { likes, dislikes } = useMemo(() => {
    const seen = new Map<string, { name: string; kind: "liked" | "disliked"; when: string }>();
    for (const log of detailQ.data ?? []) {
      for (const ex of log.exercises) {
        if (ex.feedback === "liked" || ex.feedback === "disliked") {
          const prev = seen.get(ex.exercise_id);
          if (!prev || log.started_at > prev.when) {
            seen.set(ex.exercise_id, { name: ex.exercise_name, kind: ex.feedback, when: log.started_at });
          }
        }
      }
    }
    const all = [...seen.values()];
    return { likes: all.filter((x) => x.kind === "liked"), dislikes: all.filter((x) => x.kind === "disliked") };
  }, [detailQ.data]);

  const undo = useMutation({
    mutationFn: (rid: number) => api.deleteRejection(id, rid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rejections", id] });
      qc.invalidateQueries({ queryKey: ["dash"] });
      toast("Back in the mix");
    },
  });

  const loading = rejQ.isLoading || logsQ.isLoading || detailQ.isLoading;

  return (
    <div className="stack gap-3">
      {loading && <Loader />}

      {/* Rejections */}
      <Card variant="flush">
        <div className={s.groupHead}>Won't be suggested {rejQ.data ? `· ${rejQ.data.length}` : ""}</div>
        {rejQ.data && rejQ.data.length === 0 && (
          <p className="dim" style={{ padding: "4px 14px 14px", fontSize: "0.85rem" }}>
            You haven't rejected any exercises. Tap ✕ on an exercise to remove it.
          </p>
        )}
        <div className={s.fbGroup}>
          {(rejQ.data ?? []).map((r) => (
            <div key={r.id} className={s.fbRow}>
              <span className={`${s.icon} ${s.reject}`}><X width="1em" height="1em" /></span>
              <span className="body">
                <span className="n">{r.exercise_name}</span>
                <span className="m">{reasonLabel(r.reason)} · {relTime(r.created_at)}{r.note ? ` · ${r.note}` : ""}</span>
              </span>
              <IconButton onClick={() => undo.mutate(r.id)} aria-label="Undo rejection"><RotateCcw width="1em" height="1em" /></IconButton>
            </div>
          ))}
        </div>
      </Card>

      {/* Likes */}
      {likes.length > 0 && (
        <Card variant="flush">
          <div className={s.groupHead}>You liked · {likes.length}</div>
          <div className={s.fbGroup}>
            {likes.map((x) => (
              <div key={x.name} className={s.fbRow}>
                <span className={`${s.icon} ${s.like}`}><ThumbsUp width="1em" height="1em" /></span>
                <span className="body"><span className="n">{x.name}</span><span className="m">{relTime(x.when)}</span></span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Dislikes */}
      {dislikes.length > 0 && (
        <Card variant="flush">
          <div className={s.groupHead}>You disliked · {dislikes.length}</div>
          <div className={s.fbGroup}>
            {dislikes.map((x) => (
              <div key={x.name} className={s.fbRow}>
                <span className={`${s.icon} ${s.dislike}`}><ThumbsDown width="1em" height="1em" /></span>
                <span className="body"><span className="n">{x.name}</span><span className="m">{relTime(x.when)}</span></span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {!loading && (rejQ.data?.length ?? 0) === 0 && likes.length === 0 && dislikes.length === 0 && (
        <EmptyState emoji="👍" title="No preferences yet">
          Rate exercises with 👍 👎 or ✕ while running a workout — they'll show up here.
        </EmptyState>
      )}
    </div>
  );
}
