import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { isoDaysAgo, titleCase, compact } from "../lib/format";
import { Card, SectionTitle, Loader, ErrorState, Pill, ProgressRing, Bar, Chip } from "../components/ui/primitives";
import { MuscleMap } from "../components/MuscleMap";
import {
  MuscleLinesChart, BalanceBars, ConsistencyGrid, MetricChart, PatternDonut, VolumeChart,
} from "../components/charts";
import { ChevronRight, Shield, Swap } from "../components/icons";
import s from "./Progress.module.css";

const RANGES = [
  { key: "14", label: "2w", days: 14 },
  { key: "30", label: "1mo", days: 30 },
  { key: "90", label: "3mo", days: 90 },
  { key: "180", label: "6mo", days: 180 },
  { key: "365", label: "1y", days: 365 },
  { key: "all", label: "All", days: 900 },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

const METRICS = [
  { key: "steps", label: "Steps", unit: "" },
  { key: "sleep_hours", label: "Sleep", unit: "h" },
  { key: "body_weight_kg", label: "Weight", unit: "kg" },
  { key: "active_calories", label: "Calories", unit: "" },
];

export function Progress() {
  const { userId, user } = useUser();
  const id = userId as number;
  const [range, setRange] = useState<RangeKey>("90");
  const [mapView, setMapView] = useState<"both" | "front" | "back">("both");
  const [metric, setMetric] = useState("steps");

  const days = RANGES.find((r) => r.key === range)!.days;
  const from = isoDaysAgo(days);
  const bucket = days <= 31 ? "day" : days <= 120 ? "week" : "month";
  const rq = { date_from: from };

  const summary = useQuery({ queryKey: ["dash", "summary", id, from], queryFn: () => api.dash.summary(id, rq) });
  const activation = useQuery({ queryKey: ["dash", "activation", id, from, bucket], queryFn: () => api.dash.muscleActivation(id, { ...rq, bucket, group: "body_part" }) });
  const volume = useQuery({ queryKey: ["dash", "volume", id, from, bucket], queryFn: () => api.dash.volume(id, { ...rq, bucket }) });
  const balance = useQuery({ queryKey: ["dash", "balance", id, from], queryFn: () => api.dash.balance(id, rq) });
  const patterns = useQuery({ queryKey: ["dash", "patterns", id, from], queryFn: () => api.dash.patterns(id, rq) });
  const consistency = useQuery({ queryKey: ["dash", "consistency", id, range], queryFn: () => api.dash.consistency(id, { weeks: Math.min(53, Math.ceil(days / 7)) }) });
  const subs = useQuery({ queryKey: ["dash", "subs", id, from], queryFn: () => api.dash.substitutions(id, rq) });
  const rejections = useQuery({ queryKey: ["dash", "rej", id, from], queryFn: () => api.dash.rejections(id, rq) });
  const injuries = useQuery({ queryKey: ["dash", "injuries", id], queryFn: () => api.dash.injuries(id) });
  const metricSeries = useQuery({ queryKey: ["dash", "metric", id, metric, from], queryFn: () => api.dash.metricSeries(id, metric, rq) });
  const prs = useQuery({
    queryKey: ["dash", "prs", id],
    queryFn: () => api.dash.personalRecords(id),
    enabled: !!user?.show_personal_records,
  });

  const S = summary.data;

  return (
    <div className="screen">
      <div className="stack gap-2">
        <div className="stack gap-1">
          <h1 style={{ fontSize: "clamp(1.7rem, 4.5vw, 2.3rem)" }}>Progress</h1>
          <p className="dim" style={{ fontSize: "0.9rem" }}>What your training's actually been doing.</p>
        </div>
        <div className="row gap-2 wrap">
          {RANGES.map((r) => (
            <Chip key={r.key} active={range === r.key} onClick={() => setRange(r.key)}>{r.label}</Chip>
          ))}
        </div>
      </div>

      {/* ── Summary tiles ── */}
      {summary.isLoading && <Loader />}
      {summary.isError && <ErrorState error={summary.error} retry={() => summary.refetch()} />}
      {S && (
        <>
          <div className={s.tiles}>
            <Tile label="This week" value={S.workouts.this_week} sub={`of ${S.workouts.weekly_target} target`} />
            <Tile label="Streak" value={S.workouts.current_streak_days} sub="days" />
            <Tile label="Adherence" value={S.workouts.adherence_pct != null ? Math.round(S.workouts.adherence_pct) : "—"} unit="%" sub="vs plan" />
            <Tile label="Total load" value={compact(S.training.total_activation_load)} sub={`${S.training.total_sets} sets`} />
          </div>

          <Card>
            <div className="row gap-4 center">
              <ProgressRing
                value={S.readiness.score / 100}
                size={64}
                label={S.readiness.score}
                color={S.readiness.score >= 66 ? "var(--good)" : S.readiness.score >= 45 ? "var(--warn)" : "var(--bad)"}
              />
              <div className="stack gap-1 grow">
                <SectionTitle>Training readiness — {titleCase(S.readiness.label)}</SectionTitle>
                <span className="dim" style={{ fontSize: "0.85rem" }}>{S.readiness.factors.join(" · ")}</span>
              </div>
            </div>
          </Card>
        </>
      )}

      {/* ── Muscle map ── */}
      <Card>
        <SectionTitle extra={rangeLabel(range)}>Muscle map</SectionTitle>
        <div style={{ marginTop: 12 }}>
          <MuscleMap userId={id} from={from} view={mapView} onView={setMapView} />
        </div>
        {S && (
          <p className="dim" style={{ fontSize: "0.82rem", marginTop: 6 }}>
            Hardest hit: {S.training.top_body_parts.map(titleCase).join(", ")}. Lagging:{" "}
            {S.training.undertrained_body_parts.slice(0, 3).map(titleCase).join(", ")}.
          </p>
        )}
      </Card>

      {/* ── Distribution ── */}
      <div className={`${s.split} ${s.two}`}>
        <Card>
          <SectionTitle>Muscle load over time</SectionTitle>
          {activation.isLoading && <Loader />}
          {activation.data && <div style={{ marginTop: 8 }}><MuscleLinesChart data={activation.data} /></div>}
        </Card>
        <Card>
          <SectionTitle>Where the volume goes</SectionTitle>
          {balance.data && <div style={{ marginTop: 12 }}><BalanceBars shares={balance.data.shares} /></div>}
          {balance.data && (
            <div className="row gap-3 wrap" style={{ marginTop: 12, fontSize: "0.8rem" }}>
              <span className="dim">Push : Pull <b className="mono">{balance.data.push_pull_ratio ?? "—"}</b></span>
              <span className="dim">Upper : Lower <b className="mono">{balance.data.upper_lower_ratio ?? "—"}</b></span>
            </div>
          )}
        </Card>
      </div>

      <div className={`${s.split} ${s.two}`}>
        <Card>
          <SectionTitle>Movement patterns</SectionTitle>
          {patterns.data && <div style={{ marginTop: 12 }}><PatternDonut data={patterns.data} /></div>}
        </Card>
        <Card>
          <SectionTitle>Training volume</SectionTitle>
          {volume.data && <div style={{ marginTop: 8 }}><VolumeChart data={volume.data} metric="activation_load" /></div>}
        </Card>
      </div>

      {/* ── Consistency ── */}
      <Card>
        <SectionTitle extra={consistency.data ? `${consistency.data.active_days} active days` : undefined}>Consistency</SectionTitle>
        {consistency.data && <div style={{ marginTop: 12 }}><ConsistencyGrid data={consistency.data} /></div>}
      </Card>

      {/* ── Health ── */}
      <Card>
        <SectionTitle>Daily habits</SectionTitle>
        <div className={s.metricTabs} style={{ marginTop: 10 }}>
          {METRICS.map((m) => (
            <button key={m.key} className={`vf-chip ${metric === m.key ? "on" : ""}`} onClick={() => setMetric(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
        {metricSeries.isLoading && <Loader />}
        {metricSeries.data && (
          <>
            <div style={{ marginTop: 8 }}>
              <MetricChart data={metricSeries.data} unit={METRICS.find((m) => m.key === metric)?.unit} />
            </div>
            {"avg" in metricSeries.data.summary && (
              <div className={s.miniStat} style={{ marginTop: 4 }}>
                <span className="dim">avg <b>{round(metricSeries.data.summary.avg)}</b></span>
                <span className="dim">latest <b>{round(metricSeries.data.summary.latest)}</b></span>
                <span className="dim">change <b style={{ color: metricSeries.data.summary.change < 0 ? "var(--bad)" : "var(--good)" }}>
                  {metricSeries.data.summary.change > 0 ? "+" : ""}{round(metricSeries.data.summary.change)}
                </b></span>
              </div>
            )}
          </>
        )}
        {metricSeries.data && metricSeries.data.dates.length === 0 && (
          <p className="dim" style={{ fontSize: "0.85rem", marginTop: 8 }}>
            Nothing logged yet — add it from <Link to="/profile" style={{ color: "var(--accent)", fontWeight: 600 }}>your profile</Link>.
          </p>
        )}
      </Card>

      {/* ── Safety net ── */}
      <div className={`${s.split} ${s.two}`}>
        <Card>
          <SectionTitle><Swap width="1em" height="1em" /> Safe swaps</SectionTitle>
          {subs.data && (
            <div style={{ marginTop: 10 }}>
              {subs.data.total_swaps === 0 ? (
                <p className="dim" style={{ fontSize: "0.85rem" }}>Nothing's needed swapping — your workouts fit you as-is.</p>
              ) : (
                <>
                  <div className={s.miniStat}>
                    <span className="dim"><b>{subs.data.total_swaps}</b> swaps</span>
                    <span className="dim"><b>{subs.data.swap_rate_pct}%</b> of exercises</span>
                  </div>
                  <div className={s.list} style={{ marginTop: 8 }}>
                    {subs.data.top_swapped_out.map((x) => (
                      <div key={x.exercise} className={s.listRow}><span>{x.exercise}</span><span className={s.count}>×{x.count}</span></div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </Card>
        <Card>
          <SectionTitle><Shield width="1em" height="1em" /> Pushback</SectionTitle>
          {rejections.data && (
            <div style={{ marginTop: 10 }}>
              {rejections.data.total === 0 ? (
                <p className="dim" style={{ fontSize: "0.85rem" }}>You haven't rejected anything in this window.</p>
              ) : (
                <>
                  <div className="row gap-2 wrap" style={{ marginBottom: 10 }}>
                    {Object.entries(rejections.data.by_reason).map(([r, c]) => (
                      <Pill key={r} token="plain">{titleCase(r)} {c}</Pill>
                    ))}
                  </div>
                  <div className={s.list}>
                    {rejections.data.top_exercises.map((x) => (
                      <div key={x.exercise} className={s.listRow}><span>{x.exercise}</span><span className={s.count}>×{x.count}</span></div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ── Injuries ── */}
      {injuries.data && injuries.data.injuries.length > 0 && (
        <Card>
          <SectionTitle>Injury history</SectionTitle>
          <div className={s.timeline} style={{ marginTop: 14 }}>
            {injuries.data.injuries.map((inj, i) => (
              <div key={i} className={s.tlItem}>
                <span className={s.tlDot} style={{ background: inj.ongoing ? "var(--bad)" : "var(--good)" }} />
                <div className={s.tlBody}>
                  <div className={s.tlHead}>
                    <h4>{inj.body_part}</h4>
                    <Pill token={inj.ongoing ? "bad" : "good"}>{inj.ongoing ? "Ongoing" : "Healed"}</Pill>
                  </div>
                  <span className={s.tlMeta}>
                    {inj.severity} · {inj.duration_days} days · trained {inj.workouts_during}× through it
                    {inj.workouts_before_equal_window > 0 && ` (vs ${inj.workouts_before_equal_window}× before)`}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── PRs ── */}
      {user?.show_personal_records && prs.data && prs.data.records.length > 0 && (
        <Card>
          <SectionTitle extra="max weight per lift">Personal records</SectionTitle>
          <div style={{ marginTop: 6 }}>
            {prs.data.records.slice(0, 8).map((r) => {
              const ratio = r.best_weight_kg ? r.first_weight_kg / r.best_weight_kg : 1;
              return (
                <div key={r.exercise_id} className={s.prRow}>
                  <div>
                    <div className={s.ex}>{r.exercise_name}</div>
                    <div className="dim" style={{ fontSize: "0.76rem" }}>{r.sessions} sessions</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className={s.best}>{r.best_weight_kg}<small>kg</small></div>
                    {r.gain_kg > 0 && <div className={s.gain}>+{r.gain_kg}kg</div>}
                  </div>
                  <div className={s.prog}><Bar value={1 - ratio + 0.05} /></div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Link to="/activity" style={{ display: "block" }}>
        <Card tappable className="row spread center">
          <SectionTitle>Workout history &amp; preferences</SectionTitle>
          <ChevronRight className="dim" />
        </Card>
      </Link>
    </div>
  );
}

function Tile({ label, value, unit, sub }: { label: string; value: ReactNode; unit?: string; sub?: string }) {
  return (
    <div className={s.tile}>
      <div className="eyebrow">{label}</div>
      <div className="num" style={{ fontSize: "1.7rem", lineHeight: 1.1, marginTop: 2 }}>
        {value}{unit && <span style={{ fontSize: "0.55em", color: "var(--text-dim)" }}>{unit}</span>}
      </div>
      {sub && <div className="dim" style={{ fontSize: "0.74rem" }}>{sub}</div>}
    </div>
  );
}

const round = (n: number) => (Math.abs(n) >= 100 ? Math.round(n) : Math.round(n * 10) / 10);
const rangeLabel = (k: RangeKey) => ({ "14": "last 2 weeks", "30": "last month", "90": "last 3 months", "180": "last 6 months", "365": "last year", all: "all time" }[k]);
