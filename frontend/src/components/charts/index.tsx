import { useMemo, useState, type ComponentProps } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie,
  PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import type { Consistency, MetricSeries, MuscleActivation, Patterns, VolumeSeries } from "../../lib/types";
import { fmtDate, titleCase } from "../../lib/format";
import { Bar as MiniBar } from "../ui/primitives";
import s from "./charts.module.css";

type TipFmt = ComponentProps<typeof Tooltip>["formatter"];
/** recharts 3's formatter type is loose about value being possibly-undefined;
 *  wrap so our simple (number, name) callbacks type-check. */
const fmt = (fn: (v: number, name: string) => [unknown, string]): TipFmt =>
  ((v: unknown, name: unknown) => fn(Number(v), String(name ?? ""))) as TipFmt;

export const GROUP_COLORS: Record<string, string> = {
  chest: "#e0663a", shoulders: "#e89f3c", arms: "#ccae3d", back: "#4b8f3f",
  core: "#2f9d8f", lower_back: "#3f6ea5", quads: "#6b5bb0", hamstrings: "#a05cae",
  glutes: "#c0568a", legs_other: "#8a8f9a", calves: "#5a6b7d",
};
const FALLBACK = ["#4b8f3f", "#e89f3c", "#3f6ea5", "#c0568a", "#2f9d8f", "#6b5bb0", "#e0663a", "#8a8f9a"];
const colorFor = (key: string, i: number) => GROUP_COLORS[key] ?? FALLBACK[i % FALLBACK.length];
const PRETTY: Record<string, string> = { legs_other: "Hips / Adductors", lower_back: "Lower Back", core_and_carry: "Core & Carry" };
const label = (k: string) => PRETTY[k] ?? titleCase(k);
const groupName = (k: string, d: { labels: Record<string, string> }) => PRETTY[k] ?? d.labels[k] ?? titleCase(k);

const shortDate = (iso: string) => fmtDate(iso, { month: "short", day: "numeric" });

// ── Muscle load over time — toggleable lines per body part ──
export function MuscleLinesChart({ data }: { data: MuscleActivation }) {
  const ordered = useMemo(
    () => [...data.columns].sort((a, b) => sum(data.series[b]) - sum(data.series[a])),
    [data],
  );
  // default: the 4 biggest movers on
  const [shown, setShown] = useState<Set<string>>(() => new Set(ordered.slice(0, 4)));

  const rows = data.buckets.map((b, i) => {
    const row: Record<string, number | string> = { bucket: shortDate(b) };
    for (const col of ordered) row[col] = Math.round(data.series[col]?.[i] ?? 0);
    return row;
  });

  const toggle = (c: string) =>
    setShown((cur) => {
      const n = new Set(cur);
      n.has(c) ? n.delete(c) : n.add(c);
      return n;
    });

  return (
    <div className={s.chartBox}>
      <div className={s.legend} style={{ marginTop: 0, marginBottom: 10 }}>
        {ordered.map((c, i) => (
          <button
            key={c}
            onClick={() => toggle(c)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: "0.72rem", padding: "3px 8px", borderRadius: 999,
              border: "1px solid var(--border)",
              background: shown.has(c) ? "var(--surface-2)" : "transparent",
              color: shown.has(c) ? "var(--text)" : "var(--text-faint)",
              opacity: shown.has(c) ? 1 : 0.6,
            }}
          >
            <i style={{ width: 9, height: 9, borderRadius: 3, background: shown.has(c) ? colorFor(c, i) : "var(--border-strong)" }} />
            {groupName(c, data)}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={230}>
        <LineChart data={rows} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="bucket" tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickLine={false} axisLine={false} width={34} />
          <Tooltip formatter={fmt((v, n) => [Math.round(v), groupName(n, data)])} />
          {ordered.map((c) => (
            <Line
              key={c}
              type="monotone"
              dataKey={c}
              stroke={colorFor(c, ordered.indexOf(c))}
              strokeWidth={2.4}
              dot={false}
              isAnimationActive={false}
              hide={!shown.has(c)}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="dim" style={{ fontSize: "0.72rem", marginTop: 4 }}>Tap a body part to add or remove its line.</p>
    </div>
  );
}

// ── Volume / activation-load bars ────────────────────────
export function VolumeChart({ data, metric }: { data: VolumeSeries; metric: "activation_load" | "sets" | "minutes" }) {
  const rows = data.buckets.map((b, i) => ({ bucket: shortDate(b), value: data[metric][i] ?? 0 }));
  return (
    <div className={s.chartBox}>
      <ResponsiveContainer width="100%" height={190}>
        <BarChart data={rows} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="bucket" tickLine={false} axisLine={false} minTickGap={20} />
          <YAxis tickLine={false} axisLine={false} width={40} />
          <Tooltip formatter={fmt((v) => [Math.round(v), titleCase(metric)])} cursor={{ fill: "var(--surface-2)" }} />
          <Bar dataKey="value" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={34} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Metric line + rolling average ───────────────────────
export function MetricChart({ data, unit }: { data: MetricSeries; unit?: string }) {
  const rows = data.dates.map((d, i) => ({
    date: shortDate(d),
    value: data.values[i],
    avg: data.rolling_7d[i],
  }));
  return (
    <div className={s.chartBox}>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={rows} margin={{ top: 4, right: 6, bottom: 0, left: -14 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={30} />
          <YAxis tickLine={false} axisLine={false} width={44} domain={["auto", "auto"]} />
          <Tooltip formatter={fmt((v, n) => [`${round1(v)}${unit ? " " + unit : ""}`, n === "avg" ? "7-day avg" : "daily"])} />
          <Line type="monotone" dataKey="value" stroke="var(--border-strong)" strokeWidth={1} dot={false} />
          <Line type="monotone" dataKey="avg" stroke="var(--accent)" strokeWidth={2.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Consistency calendar ─────────────────────────────────
export function ConsistencyGrid({ data }: { data: Consistency }) {
  const start = new Date(data.start + "T00:00:00");
  const end = new Date(data.end + "T00:00:00");
  // pad to week start (Mon)
  const pad = (start.getDay() + 6) % 7;
  const days: (string | null)[] = Array(pad).fill(null);
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    days.push(d.toLocaleDateString("en-CA"));
  }
  const max = Math.max(1, ...Object.values(data.counts));
  const shade = (n: number) => {
    if (!n) return "var(--surface-3)";
    const t = 0.35 + 0.65 * (n / max);
    return `color-mix(in srgb, var(--accent) ${Math.round(t * 100)}%, var(--surface-3))`;
  };

  return (
    <div className={s.calWrap}>
      <div className={s.calendar}>
        {days.map((iso, i) => (
          <div
            key={i}
            className={s.cell}
            style={{ background: iso ? shade(data.counts[iso] ?? 0) : "transparent" }}
            title={iso ? `${shortDate(iso)} — ${data.counts[iso] ?? 0} workout${(data.counts[iso] ?? 0) === 1 ? "" : "s"}` : undefined}
          />
        ))}
      </div>
      <div className={s.calScale}>
        less
        {[0, 0.4, 0.7, 1].map((t) => (
          <i key={t} style={{ background: t === 0 ? "var(--surface-3)" : `color-mix(in srgb, var(--accent) ${35 + t * 65}%, var(--surface-3))` }} />
        ))}
        more
      </div>
    </div>
  );
}

// ── Movement-pattern donut ──────────────────────────────
export function PatternDonut({ data }: { data: Patterns }) {
  const rows = Object.entries(data.shares).map(([name, value], i) => ({ name, value, fill: colorFor(name, i + 3) }));
  if (!rows.length) return <p className="dim" style={{ fontSize: "0.85rem" }}>No pattern data yet.</p>;
  return (
    <div className={s.donutWrap}>
      <ResponsiveContainer width={140} height={140}>
        <PieChart>
          <Pie data={rows} dataKey="value" innerRadius={40} outerRadius={66} paddingAngle={2} stroke="none">
            {rows.map((r) => <Cell key={r.name} fill={r.fill} />)}
          </Pie>
          <Tooltip formatter={fmt((v, n) => [`${round1(v)}%`, label(n)])} />
        </PieChart>
      </ResponsiveContainer>
      <div className={s.legend} style={{ flexDirection: "column", gap: 6, marginTop: 0 }}>
        {rows.map((r) => (
          <span key={r.name}><i style={{ background: r.fill }} /> {label(r.name)} <span className="mono dim">{round1(r.value)}%</span></span>
        ))}
      </div>
    </div>
  );
}

// ── Body-part balance bars ──────────────────────────────
export function BalanceBars({ shares }: { shares: Record<string, number> }) {
  const rows = Object.entries(shares);
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <div className={s.hbars}>
      {rows.map(([name, v], i) => (
        <div key={name} className={s.hbar}>
          <span className={s.lbl}>{label(name)}</span>
          <MiniBar value={v / max} color={colorFor(name, i)} />
          <span className={s.val}>{round1(v)}%</span>
        </div>
      ))}
    </div>
  );
}

const sum = (a?: number[]) => (a ? a.reduce((x, y) => x + y, 0) : 0);
const round1 = (n: number) => Math.round(n * 10) / 10;
