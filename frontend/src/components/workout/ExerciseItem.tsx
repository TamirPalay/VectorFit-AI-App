import { useState } from "react";
import type { WorkoutExercise } from "../../lib/types";
import { prescription, titleCase } from "../../lib/format";
import { Check, Swap, ThumbsDown, ThumbsUp, X } from "../icons";
import { AiBadge } from "../ui/AiNote";
import s from "./ExerciseItem.module.css";

export type FB = "liked" | "disliked" | "rejected" | null;

interface Props {
  ex: WorkoutExercise;
  index: number;
  description?: string;
  /** tick box (Today / runner) */
  checked?: boolean;
  onToggle?: () => void;
  /** feedback controls — always shown when provided */
  feedback?: FB;
  rejectReason?: string | null;
  onFeedback?: (fb: FB) => void;
  /** open a detail sheet for this exercise */
  onOpen?: () => void;
}

export function ExerciseItem({
  ex, index, description, checked, onToggle, feedback, rejectReason, onFeedback, onOpen,
}: Props) {
  const [openNote, setOpenNote] = useState(false);
  const swapped = !!ex.substituted_for_name;
  const isRejected = feedback === "rejected";

  const NameEl = onOpen ? "button" : "span";

  return (
    <div className={`${s.item} ${checked ? s.done : ""} ${isRejected ? s.rejected : ""}`}>
      {onToggle ? (
        <button className={`${s.check} ${checked ? s.on : ""}`} onClick={onToggle}
          aria-label={checked ? "Mark not done" : "Mark done"} aria-pressed={!!checked} disabled={isRejected}>
          <Check width="0.9em" height="0.9em" />
        </button>
      ) : (
        <span className={s.index}>{index + 1}</span>
      )}

      <div className={s.body}>
        <NameEl className={onOpen ? s.nameBtn : undefined} onClick={onOpen}>
          <span className={s.name}>
            {swapped && <span className={s.struck}>{ex.substituted_for_name}</span>}
            {swapped && "→ "}
            {ex.exercise_name}
          </span>
        </NameEl>
        <span className={s.meta}>
          <span>{prescription(ex)}</span>
          {ex.rest_seconds ? <span className={s.rest}>{ex.rest_seconds}s</span> : null}
        </span>
        {ex.notes && <span className={s.note}>{ex.notes}</span>}
        {description && <span className={s.desc}>{description}</span>}

        {isRejected && (
          <span className={s.rejTag}>
            <X width="0.8em" height="0.8em" /> Won't suggest again{rejectReason ? ` · ${titleCase(rejectReason)}` : ""}
          </span>
        )}
        {feedback === "disliked" && (
          <span className={s.rejTag} style={{ color: "var(--warn)" }}>
            <ThumbsDown width="0.8em" height="0.8em" /> Fewer of these — still eligible, just deprioritised
          </span>
        )}

        {swapped && (
          <>
            <button className={s.swapBtn} onClick={() => setOpenNote((o) => !o)}>
              <Swap width="0.9em" height="0.9em" /> Why the swap?
            </button>
            {openNote && (
              <div className={s.swapNote}>
                <AiBadge kind="ai" title="Written by the AI coach; the swap itself was chosen by the substitution engine" />{" "}
                {ex.substitution_note || (
                  <>Swapped from <span className={s.from}>{ex.substituted_for_name}</span> to keep you training safely around your injury.</>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {onFeedback && (
        <div className={s.fb}>
          <button className={`${s.fbBtn} ${s.up} ${feedback === "liked" ? s.on : ""}`}
            aria-label="Like — more like this" title="Like — keep suggesting these"
            onClick={() => onFeedback(feedback === "liked" ? null : "liked")}>
            <ThumbsUp width="0.95em" height="0.95em" />
          </button>
          <button className={`${s.fbBtn} ${s.down} ${feedback === "disliked" ? s.on : ""}`}
            aria-label="Fewer of these" title="Fewer of these — stays eligible, just deprioritised (−0.15)"
            onClick={() => onFeedback(feedback === "disliked" ? null : "disliked")}>
            <ThumbsDown width="0.95em" height="0.95em" />
          </button>
          <button className={`${s.fbBtn} ${s.rej} ${isRejected ? s.on : ""}`}
            aria-label="Don't suggest this again" title="Don't suggest again — pick a reason; may be blocked or cooled down"
            onClick={() => onFeedback(isRejected ? null : "rejected")}>
            <X width="0.95em" height="0.95em" />
          </button>
        </div>
      )}
    </div>
  );
}
