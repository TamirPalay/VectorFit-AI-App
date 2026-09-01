import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { Button, Pill, Spinner } from "../components/ui/primitives";
import { Sheet } from "../components/ui/Sheet";
import { ChevronRight, Trash } from "../components/icons";
import { useToast } from "../components/ui/Toast";
import { titleCase } from "../lib/format";
import type { User } from "../lib/types";
import s from "./Onboarding.module.css";

const initials = (n: string) => n.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

function story(u: User): string {
  const inj = u.injuries.find((i) => !i.healed_at);
  const bits = [`${u.age ?? "—"} · ${titleCase(u.fitness_level)}`];
  if (inj) bits.push(`recovering a ${inj.body_part} injury`);
  else bits.push("no injuries");
  return bits.join(" · ");
}

export function Onboarding() {
  const { setUserId } = useUser();
  const qc = useQueryClient();
  const toast = useToast();
  const [showCreate, setShowCreate] = useState(false);

  const usersQ = useQuery({ queryKey: ["users-list"], queryFn: () => api.listUsers(), retry: 0 });
  const loading = usersQ.isLoading;
  const users = usersQ.data ?? [];

  const del = useMutation({
    mutationFn: (uid: number) => api.deleteUser(uid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users-list"] }); toast("Profile deleted"); },
    onError: (e: Error) => toast(e.message, "err"),
  });

  return (
    <div className={s.wrap}>
      <div className={s.inner}>
        <div className={s.hero}>
          <span className={s.mark}>◆</span>
          <h1>VectorFit</h1>
          <p>
            Workouts that adapt to your injuries, your soreness, and what you actually
            like doing — and always keep a safe alternative ready.
          </p>
        </div>

        <span className={s.pickLabel}>Continue as</span>

        <div className={s.profiles}>
          {loading && (
            <div style={{ display: "grid", placeItems: "center", padding: 32 }}><Spinner /></div>
          )}
          {users.map((u) => {
            const inj = u.injuries.find((i) => !i.healed_at);
            return (
              <div key={u.id} className={s.profileRow}>
                <button className={s.profile} onClick={() => setUserId(u.id)}>
                  <span className={s.av}>{initials(u.name)}</span>
                  <span className={s.meta}>
                    <span className="row spread gap-2">
                      <span className={s.name}>{u.name}</span>
                      {inj ? <Pill token="bad" dot>{titleCase(inj.body_part)}</Pill> : <Pill token="good" dot>Clear</Pill>}
                    </span>
                    <span className={s.story}>{story(u)}</span>
                  </span>
                  <ChevronRight className={s.chev} />
                </button>
                <button
                  className={s.del}
                  title={`Delete ${u.name}`}
                  aria-label={`Delete ${u.name}`}
                  disabled={del.isPending}
                  onClick={() => {
                    if (confirm(`Delete "${u.name}" and all their workouts, metrics and preferences? This can't be undone.`)) {
                      del.mutate(u.id);
                    }
                  }}
                >
                  <Trash width="1em" height="1em" />
                </button>
              </div>
            );
          })}
          {!loading && users.length === 0 && (
            <p className="dim" style={{ textAlign: "center", fontSize: "0.85rem" }}>
              No demo profiles found — is the backend running and seeded?
            </p>
          )}
        </div>

        <div className={s.createRow}>
          <span className={s.rule} /><span>or</span><span className={s.rule} />
        </div>
        <Button variant="secondary" block onClick={() => setShowCreate(true)}>
          Create your own profile
        </Button>
      </div>

      {showCreate && <CreateProfile onClose={() => setShowCreate(false)} onCreated={setUserId} />}
    </div>
  );
}

const GOALS = ["general_fitness", "strength", "muscle_gain", "hypertrophy", "endurance", "weight_loss", "mobility", "sport_specific"];
const EQUIP = ["bodyweight", "dumbbells", "barbell", "kettlebell", "pull_up_bar", "resistance_bands", "cables", "machines", "bench", "squat_rack"];

function CreateProfile({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [level, setLevel] = useState<"beginner" | "intermediate" | "advanced">("beginner");
  const [days, setDays] = useState(3);
  const [mins, setMins] = useState(45);
  const [goals, setGoals] = useState<string[]>(["general_fitness"]);
  const [equipment, setEquipment] = useState<string[]>(["bodyweight", "dumbbells"]);

  const toggle = (arr: string[], v: string, set: (a: string[]) => void) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const create = useMutation({
    mutationFn: () =>
      api.createUser({
        name: name.trim(),
        email: `${name.trim().toLowerCase().replace(/\s+/g, ".")}.${Date.now()}@vectorfit.app`,
        fitness_level: level,
        experience_level: level,
        days_per_week: days,
        minutes_per_session: mins,
        goals,
        equipment,
      }),
    onSuccess: (u) => {
      qc.setQueryData(["users-list"], (prev: User[] | undefined) => [...(prev ?? []), u]);
      qc.invalidateQueries({ queryKey: ["users-list"] });
      onCreated(u.id);
      onClose();
    },
  });

  return (
    <Sheet
      open
      onClose={onClose}
      title="New profile"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>
            Create &amp; continue
          </Button>
        </>
      }
    >
      <div className="stack gap-4">
        <label className="stack gap-1">
          <span className="eyebrow">Name</span>
          <input className="vf-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex" autoFocus />
        </label>

        <div className="stack gap-2">
          <span className="eyebrow">Experience</span>
          <div className="row gap-2 wrap">
            {(["beginner", "intermediate", "advanced"] as const).map((l) => (
              <button key={l} type="button"
                className={`vf-chip ${level === l ? "on" : ""}`}
                onClick={() => setLevel(l)}>{titleCase(l)}</button>
            ))}
          </div>
        </div>

        <div className="row gap-4 wrap">
          <label className="stack gap-1" style={{ flex: 1, minWidth: 130 }}>
            <span className="eyebrow">Days / week</span>
            <input type="number" min={1} max={7} className="vf-input" value={days}
              onChange={(e) => setDays(Math.min(7, Math.max(1, +e.target.value || 3)))} />
          </label>
          <label className="stack gap-1" style={{ flex: 1, minWidth: 130 }}>
            <span className="eyebrow">Minutes / session</span>
            <input type="number" min={10} max={180} step={5} className="vf-input" value={mins}
              onChange={(e) => setMins(Math.min(180, Math.max(10, +e.target.value || 45)))} />
          </label>
        </div>

        <div className="stack gap-2">
          <span className="eyebrow">Goals</span>
          <div className="row gap-2 wrap">
            {GOALS.map((g) => (
              <button key={g} type="button" className={`vf-chip ${goals.includes(g) ? "on" : ""}`}
                onClick={() => toggle(goals, g, setGoals)}>{titleCase(g)}</button>
            ))}
          </div>
        </div>

        <div className="stack gap-2">
          <span className="eyebrow">Equipment</span>
          <div className="row gap-2 wrap">
            {EQUIP.map((e) => (
              <button key={e} type="button" className={`vf-chip ${equipment.includes(e) ? "on" : ""}`}
                onClick={() => toggle(equipment, e, setEquipment)}>{titleCase(e)}</button>
            ))}
          </div>
        </div>

        {create.isError && <p style={{ color: "var(--bad)", fontSize: "0.85rem" }}>{(create.error as Error).message}</p>}
      </div>
    </Sheet>
  );
}
