import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { ApiError } from "../../lib/api";
import s from "./primitives.module.css";

const cx = (...c: (string | false | undefined | null)[]) => c.filter(Boolean).join(" ");

// ── Card ──────────────────────────────────────────────────
type CardProps = HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "inset" | "flush";
  pad?: boolean;
  tappable?: boolean;
};
export function Card({ variant = "default", pad = true, tappable, className, ...rest }: CardProps) {
  return (
    <div
      className={cx(
        s.card,
        variant === "inset" && s.inset,
        variant === "flush" ? s.flush : pad && s.pad,
        tappable && s.tappable,
        className,
      )}
      {...rest}
    />
  );
}

export function SectionTitle({ children, extra }: { children: ReactNode; extra?: ReactNode }) {
  return (
    <div className={s.sectionTitle}>
      <span>{children}</span>
      {extra && <small>{extra}</small>}
    </div>
  );
}

// ── Button ────────────────────────────────────────────────
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  block?: boolean;
  loading?: boolean;
};
export function Button({
  variant = "primary", size = "md", block, loading, disabled, className, children, ...rest
}: BtnProps) {
  return (
    <button
      className={cx(s.btn, s[variant], size === "sm" && s.sm, size === "lg" && s.lg, block && s.block, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <span className={s.spinner} style={{ width: 15, height: 15, borderWidth: 2 }} />}
      {children}
    </button>
  );
}

export function IconButton({ className, title, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  // Icon-only buttons carry an aria-label for screen readers; mirror it into a
  // native title so sighted users get the same hover hint for free.
  return (
    <button
      className={cx(s.iconBtn, className)}
      title={title ?? rest["aria-label"]}
      {...rest}
    />
  );
}

// ── Chip ──────────────────────────────────────────────────
export function Chip({
  active, count, onClick, children,
}: { active?: boolean; count?: number; onClick?: () => void; children: ReactNode }) {
  return (
    <button type="button" className={cx(s.chip, active && s.on)} onClick={onClick} aria-pressed={!!active}>
      {children}
      {count != null && <span className={s.count}>{count}</span>}
    </button>
  );
}

// ── Pill (status badge) ───────────────────────────────────
type Token = "good" | "warn" | "bad" | "pref" | "info" | "plain";
export function Pill({ token = "plain", dot, children }: { token?: Token; dot?: boolean; children: ReactNode }) {
  return (
    <span className={cx(s.pill, s[token])}>
      {dot && <span className={s.dot} />}
      {children}
    </span>
  );
}

// ── Stat tile ─────────────────────────────────────────────
export function Stat({
  label, value, unit, sub,
}: { label: string; value: ReactNode; unit?: string; sub?: ReactNode }) {
  return (
    <div className={s.stat}>
      <span className={s.label}>{label}</span>
      <span className={s.value}>
        {value}
        {unit && <span className={s.unit}>{unit}</span>}
      </span>
      {sub && <span className={s.sub}>{sub}</span>}
    </div>
  );
}

// ── Segmented control ─────────────────────────────────────
export function Segmented<T extends string>({
  options, value, onChange,
}: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className={s.segmented} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          className={o.value === value ? s.on : undefined}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── Feedback ──────────────────────────────────────────────
export function Spinner() {
  return <span className={s.spinner} />;
}

export function Loader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className={s.loader}>
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  emoji = "🗒️", title, children, action,
}: { emoji?: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={s.empty}>
      <span className={s.emoji}>{emoji}</span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg =
    error instanceof ApiError
      ? error.status === 0
        ? "Can't reach the server. Is the backend running on port 8000?"
        : error.message
      : error instanceof Error
        ? error.message
        : "Something went wrong.";
  return (
    <div className={s.errorBox}>
      <strong>Couldn't load this.</strong> {msg}
      {retry && (
        <>
          {" "}
          <button onClick={retry} style={{ textDecoration: "underline", fontWeight: 600 }}>
            Try again
          </button>
        </>
      )}
    </div>
  );
}

// ── Progress ring ─────────────────────────────────────────
export function ProgressRing({
  value, size = 56, stroke = 6, label, color = "var(--accent)",
}: { value: number; size?: number; stroke?: number; label?: ReactNode; color?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <span className={s.ring} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - clamped)}
          style={{ transition: "stroke-dashoffset 500ms ease" }}
        />
      </svg>
      {label != null && <span className={s.ringLabel} style={{ fontSize: size / 3.6 }}>{label}</span>}
    </span>
  );
}

// ── Mini bar meter ────────────────────────────────────────
export function Bar({ value, color }: { value: number; color?: string }) {
  return (
    <span className={s.bar}>
      <span style={{ width: `${Math.max(2, Math.min(100, value * 100))}%`, background: color }} />
    </span>
  );
}

export { cx };
