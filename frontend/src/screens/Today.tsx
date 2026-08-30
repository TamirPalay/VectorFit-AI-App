import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { useUser } from "../context/UserContext";
import { fmtDate } from "../lib/format";
import { Button, Card, Loader, ErrorState, ProgressRing } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { SessionRunner } from "../components/workout/SessionRunner";
import { Flame, Sparkles } from "../components/icons";
import s from "./Today.module.css";

export function Today() {
  const { userId, user } = useUser();
  const id = userId as number;
  const qc = useQueryClient();
  const toast = useToast();

  const todayQ = useQuery({ queryKey: ["today", id], queryFn: () => api.today(id), retry: false });
  const summaryQ = useQuery({ queryKey: ["dash", "summary", id], queryFn: () => api.dash.summary(id), staleTime: 120_000 });

  const generate = useMutation({
    mutationFn: () => api.generateToday(id),
    onSuccess: (d) => {
      qc.setQueryData(["today", id], d);
      toast(d.is_rest ? "Rest day scheduled" : "Today's workout is ready");
    },
    onError: (e: Error) => toast(e.message, "err"),
  });

  const notFound = todayQ.error instanceof ApiError && todayQ.error.status === 404;
  const day = todayQ.data;
  const S = summaryQ.data;

  return (
    <div className="screen">
      <div className={s.hero}>
        <span className={s.date}>
          {fmtDate(new Date().toISOString(), { weekday: "long", month: "long", day: "numeric" })}
        </span>
        <h1>{greeting(user?.name)}</h1>
        <span className={s.sub}>
          {day?.is_rest
            ? "Recovery is training too."
            : day?.workout
              ? `${day.workout.workout_label ?? "Workout"} — ${day.workout.exercises.length} exercises`
              : "Ready when you are."}
        </span>

        {S && (
          <div className={s.readiness}>
            <ProgressRing
              value={S.readiness.score / 100}
              size={58}
              label={S.readiness.score}
              color={ringColor(S.readiness.score)}
            />
            <div className={s.facts}>
              <strong>{cap(S.readiness.label)}</strong> to train
              <br />
              {S.readiness.factors.slice(0, 2).join(" · ")}
              {S.workouts.current_streak_days > 0 && (
                <> · <Flame width="0.9em" height="0.9em" style={{ display: "inline", verticalAlign: "-2px" }} /> {S.workouts.current_streak_days}-day streak</>
              )}
            </div>
          </div>
        )}
      </div>

      {todayQ.isLoading && <Loader label="Checking today's plan…" />}

      {notFound && (
        <Card className="stack gap-4" style={{ alignItems: "center", textAlign: "center", padding: 32 }}>
          <Sparkles style={{ color: "var(--accent)", width: "2em", height: "2em" }} />
          <div className="stack gap-1">
            <h2>No workout yet for today</h2>
            <p className="dim" style={{ fontSize: "0.88rem", maxWidth: "32ch" }}>
              We'll pick a type from your goals, recent training, and what your body can handle right now.
            </p>
          </div>
          <Button size="lg" loading={generate.isPending} onClick={() => generate.mutate()}>
            Generate today's workout
          </Button>
        </Card>
      )}

      {todayQ.isError && !notFound && <ErrorState error={todayQ.error} retry={() => todayQ.refetch()} />}

      {day && (day.is_rest ? (
        <Card className={s.restCard}>
          <span className={s.big}>🌙</span>
          <h2>Rest day</h2>
          <p>You've hit your training target for the week. Light movement and a walk are perfect today.</p>
          <Button variant="secondary" size="sm" loading={generate.isPending} onClick={() => generate.mutate()}>
            Train anyway
          </Button>
        </Card>
      ) : day.workout ? (
        <SessionRunner
          log={day.workout}
          userId={id}
          warnings={day.warnings}
          onChange={(updated) => qc.setQueryData(["today", id], { ...day, workout: updated })}
        />
      ) : null)}
    </div>
  );
}

function greeting(name?: string) {
  const h = new Date().getHours();
  const g = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return name ? `${g}, ${name.split(" ")[0]}` : g;
}
const cap = (str: string) => str[0].toUpperCase() + str.slice(1);
const ringColor = (n: number) => (n >= 66 ? "var(--good)" : n >= 45 ? "var(--warn)" : "var(--bad)");
