import { Sheet } from "../ui/Sheet";
import { titleCase } from "../../lib/format";

const REASONS: { value: string; label: string; hint: string }[] = [
  { value: "dont_like", label: "Don't like it", hint: "just not for me" },
  { value: "too_hard", label: "Too hard", hint: "needs regressing" },
  { value: "too_easy", label: "Too easy", hint: "needs progressing" },
  { value: "bad_form", label: "Unsure on form", hint: "not confident with technique" },
  { value: "too_sore", label: "Too sore", hint: "3-day cooldown" },
  { value: "no_equipment", label: "No equipment", hint: "can't do it right now" },
  { value: "too_long", label: "Takes too long", hint: "time constraint" },
  { value: "other", label: "Other", hint: "" },
];

export function ReasonPicker({
  exerciseName, onPick, onClose,
}: {
  exerciseName: string;
  onPick: (reason: string) => void;
  onClose: () => void;
}) {
  return (
    <Sheet open onClose={onClose} title={`Why skip ${exerciseName}?`}>
      <p className="dim" style={{ fontSize: "0.85rem", marginBottom: 12 }}>
        This tells the planner how to adjust future workouts.
      </p>
      <div style={{ display: "grid", gap: 8 }}>
        {REASONS.map((r) => (
          <button
            key={r.value}
            onClick={() => { onPick(r.value); onClose(); }}
            style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "13px 14px", borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)", background: "var(--surface-2)",
              fontWeight: 600, fontSize: "0.92rem", textAlign: "left",
            }}
          >
            {r.label}
            {r.hint && <span className="dim" style={{ fontWeight: 400, fontSize: "0.76rem" }}>{r.hint}</span>}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

export const reasonLabel = (v: string) =>
  REASONS.find((r) => r.value === v)?.label ?? titleCase(v);
