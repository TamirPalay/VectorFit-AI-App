import { useState, type ReactNode } from "react";
import { Sparkles } from "../icons";
import s from "./AiNote.module.css";

/**
 * A visible marker for every place the app's AI does something — the LLM coach
 * or the deterministic suggestibility / substitution / scheduling engines.
 * The goal is that a user can always *see and feel* which step was automated
 * and why, rather than it happening invisibly.
 *
 * `kind`:
 *  - "ai"     → an LLM wrote this (explanations, swap narration)
 *  - "engine" → a deterministic rules engine decided this (injury blocks,
 *               substitutions, workout-type scheduling, readiness)
 *  - "math"   → pure arithmetic on the data (muscle-map projection, minutes)
 */
export function AiNote({
  kind = "ai",
  children,
  details,
  plain,
}: {
  kind?: "ai" | "engine" | "math";
  children: ReactNode;
  details?: ReactNode;
  plain?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const tag = kind === "ai" ? "AI coach" : kind === "engine" ? "Safety engine" : "Computed";
  return (
    <div className={`${s.note} ${plain ? s.plain : ""}`}>
      <Sparkles className={s.icon} width="1em" height="1em" />
      <div className={s.body}>
        <span className={s.tag}>{tag}</span>
        {children}
        {details && (
          <>
            <button className={s.detailsBtn} onClick={() => setOpen((o) => !o)}>
              {open ? "Hide details" : "How this works"}
            </button>
            {open && <div className={s.details}>{details}</div>}
          </>
        )}
      </div>
    </div>
  );
}

/** Compact inline badge — put next to a section heading whose content is AI/engine-driven. */
export function AiBadge({ kind = "ai", title }: { kind?: "ai" | "engine" | "math"; title?: string }) {
  const label = kind === "ai" ? "AI" : kind === "engine" ? "Engine" : "Auto";
  return (
    <span
      className={s.badge}
      title={title ?? (kind === "ai"
        ? "Written by the AI coach from your data"
        : kind === "engine"
          ? "Decided by the rules engine (injuries, cooldowns, substitutions)"
          : "Calculated directly from the exercise data")}
    >
      <Sparkles width="0.8em" height="0.8em" /> {label}
    </span>
  );
}
