import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { titleCase, todayISO, fmtDate } from "../lib/format";
import { Button, Card, SectionTitle, Pill, IconButton } from "../components/ui/primitives";
import { Sheet } from "../components/ui/Sheet";
import { useToast } from "../components/ui/Toast";
import { Check, Plus, Shield } from "../components/icons";
import type { Injury } from "../lib/types";
import s from "./Profile.module.css";

const GOALS = ["general_fitness", "strength", "muscle_gain", "hypertrophy", "endurance", "weight_loss", "mobility", "sport_specific"];
const EQUIP = ["bodyweight", "dumbbells", "barbell", "kettlebell", "pull_up_bar", "resistance_bands", "cables", "machines", "bench", "squat_rack"];
const BODY_PARTS = ["right shoulder", "left shoulder", "lower back", "left knee", "right knee", "left elbow", "right elbow", "left wrist", "right wrist", "neck", "left ankle", "right ankle", "left hip", "right hip", "left hamstring", "right hamstring"];

const initials = (n: string) => n.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function Profile() {
  const { userId, user, clearUser } = useUser();
  const id = userId as number;
  const qc = useQueryClient();
  const toast = useToast();
  const [editBasics, setEditBasics] = useState(false);
  const [addInjury, setAddInjury] = useState(false);

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateUser(id, body),
    onSuccess: (u) => { qc.setQueryData(["user", id], u); },
    onError: (e: Error) => toast(e.message, "err"),
  });
  const heal = useMutation({
    mutationFn: (injuryId: number) => api.healInjury(id, injuryId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["user", id] }); toast("Marked as healed"); },
  });

  if (!user) return null;
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  return (
    <div className="screen">
      <div className="screen-head"><h1>Profile</h1><p>The app plans around everything here.</p></div>

      <Card>
        <div className={s.idCard}>
          <span className={s.av}>{initials(user.name)}</span>
          <div className="who grow">
            <div className="nm">{user.name}</div>
            <div className="meta">{user.age ? `${user.age} · ` : ""}{titleCase(user.fitness_level)}</div>
          </div>
          <Button size="sm" variant="secondary" onClick={() => setEditBasics(true)}>Edit</Button>
        </div>
        <div className={s.kv}>
          <div><span className="k">Per week</span><span className="v">{user.days_per_week}<span style={{ fontSize: "0.5em", color: "var(--text-dim)" }}> days</span></span></div>
          <div><span className="k">Session</span><span className="v">{user.minutes_per_session}<span style={{ fontSize: "0.5em", color: "var(--text-dim)" }}> min</span></span></div>
        </div>
      </Card>

      <Card>
        <SectionTitle>Goals</SectionTitle>
        <div className="row gap-2 wrap" style={{ marginTop: 10 }}>
          {GOALS.map((g) => (
            <button key={g} className={`vf-chip ${user.goals.includes(g) ? "on" : ""}`}
              onClick={() => patch.mutate({ goals: toggle(user.goals, g) })}>
              {titleCase(g)}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <SectionTitle>Equipment</SectionTitle>
        <div className="row gap-2 wrap" style={{ marginTop: 10 }}>
          {EQUIP.map((e) => (
            <button key={e} className={`vf-chip ${user.equipment.includes(e) ? "on" : ""}`}
              onClick={() => patch.mutate({ equipment: toggle(user.equipment, e) })}>
              {titleCase(e)}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <div className="row spread center">
          <SectionTitle><Shield width="1em" height="1em" /> Injuries</SectionTitle>
          <IconButton onClick={() => setAddInjury(true)} aria-label="Add injury"><Plus /></IconButton>
        </div>
        <div style={{ marginTop: 6 }}>
          {user.injuries.length === 0 && <p className="dim" style={{ fontSize: "0.85rem", padding: "8px 0" }}>None — nice.</p>}
          {user.injuries.map((inj) => (
            <div key={inj.id} className={s.injRow}>
              <div className="id">
                <div className="bp">{inj.body_part}</div>
                <div className="sub">
                  {titleCase(inj.severity)}
                  {inj.healed_at
                    ? ` · healed ${fmtDate(inj.healed_at)}`
                    : inj.expected_recovery_date
                      ? ` · expected back ${fmtDate(inj.expected_recovery_date)}`
                      : ""}
                </div>
              </div>
              {inj.healed_at
                ? <Pill token="good" dot>Healed</Pill>
                : <Button size="sm" variant="secondary" loading={heal.isPending} onClick={() => heal.mutate(inj.id)}>
                    <Check width="0.9em" height="0.9em" /> Healed
                  </Button>}
            </div>
          ))}
        </div>
      </Card>

      <TodayHabits userId={id} />

      <Card>
        <div className={s.toggleRow}>
          <div>
            <SectionTitle>Show personal records</SectionTitle>
            <div className={s.desc}>Track your best weight per lift. Turn off if you don't train for load.</div>
          </div>
          <button
            className={`${s.switch} ${user.show_personal_records ? s.on : ""}`}
            role="switch"
            aria-checked={user.show_personal_records}
            onClick={() => patch.mutate({ show_personal_records: !user.show_personal_records })}
          />
        </div>
      </Card>

      <Button variant="secondary" block onClick={clearUser}>Switch profile</Button>

      {editBasics && <EditBasics onClose={() => setEditBasics(false)} onSave={(b) => { patch.mutate(b); setEditBasics(false); }} user={user} />}
      {addInjury && <AddInjury userId={id} onClose={() => setAddInjury(false)} onDone={() => { qc.invalidateQueries({ queryKey: ["user", id] }); setAddInjury(false); }} />}
    </div>
  );
}

// ── Today's habit logger ─────────────────────────────────
function TodayHabits({ userId }: { userId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const day = todayISO();
  const q = useQuery({ queryKey: ["metric", userId, day], queryFn: () => api.metrics(userId, { date_from: day, date_to: day }) });
  const cur = q.data?.[0];

  const [steps, setSteps] = useState("");
  const [sleep, setSleep] = useState("");
  const [weight, setWeight] = useState("");
  const [energy, setEnergy] = useState<number | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {};
      if (steps) body.steps = Math.round(+steps);
      if (sleep) body.sleep_hours = +sleep;
      if (weight) body.body_weight_kg = +weight;
      if (energy) body.energy_level = energy;
      return api.putMetric(userId, day, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["metric", userId] });
      qc.invalidateQueries({ queryKey: ["dash"] });
      toast("Logged for today");
      setSteps(""); setSleep(""); setWeight(""); setEnergy(null);
    },
  });

  const dirty = steps || sleep || weight || energy;

  return (
    <Card>
      <SectionTitle extra={cur ? "updates today's entry" : undefined}>Log today</SectionTitle>
      <div className={s.habitGrid} style={{ marginTop: 12 }}>
        <label className={s.habit}>
          <span>Steps {cur?.steps ? `· now ${cur.steps}` : ""}</span>
          <input className="vf-input" inputMode="numeric" value={steps} onChange={(e) => setSteps(e.target.value)} placeholder="8000" />
        </label>
        <label className={s.habit}>
          <span>Sleep (h) {cur?.sleep_hours ? `· now ${cur.sleep_hours}` : ""}</span>
          <input className="vf-input" inputMode="decimal" value={sleep} onChange={(e) => setSleep(e.target.value)} placeholder="7.5" />
        </label>
        <label className={s.habit}>
          <span>Weight (kg) {cur?.body_weight_kg ? `· now ${cur.body_weight_kg}` : ""}</span>
          <input className="vf-input" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="72" />
        </label>
        <div className={s.habit}>
          <span>Energy {cur?.energy_level ? `· now ${cur.energy_level}` : ""}</span>
          <div className={s.energyDots}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={energy === n ? s.on : ""} onClick={() => setEnergy(energy === n ? null : n)}>{n}</button>
            ))}
          </div>
        </div>
      </div>
      <Button block style={{ marginTop: 14 }} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
        Save
      </Button>
    </Card>
  );
}

// ── Edit basics sheet ────────────────────────────────────
function EditBasics({
  user, onClose, onSave,
}: {
  user: { name: string; age: number | null; fitness_level: string; days_per_week: number; minutes_per_session: number };
  onClose: () => void;
  onSave: (b: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(user.name);
  const [age, setAge] = useState(user.age ?? 30);
  const [level, setLevel] = useState(user.fitness_level);
  const [days, setDays] = useState(user.days_per_week);
  const [mins, setMins] = useState(user.minutes_per_session);

  return (
    <Sheet open onClose={onClose} title="Edit profile"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={() => onSave({ name: name.trim(), age, fitness_level: level, experience_level: level, days_per_week: days, minutes_per_session: mins })}>Save</Button></>}>
      <div className="stack gap-4">
        <label className="stack gap-1"><span className="eyebrow">Name</span>
          <input className="vf-input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <div className="row gap-4">
          <label className="stack gap-1 grow"><span className="eyebrow">Age</span>
            <input type="number" className="vf-input" value={age} onChange={(e) => setAge(+e.target.value || 30)} /></label>
        </div>
        <div className="stack gap-2"><span className="eyebrow">Experience</span>
          <div className="row gap-2">
            {["beginner", "intermediate", "advanced"].map((l) => (
              <button key={l} className={`vf-chip ${level === l ? "on" : ""}`} onClick={() => setLevel(l)}>{titleCase(l)}</button>
            ))}
          </div>
        </div>
        <label className="stack gap-2"><span className="eyebrow">Days / week — {days}</span>
          <input type="range" min={1} max={7} value={days} onChange={(e) => setDays(+e.target.value)} /></label>
        <label className="stack gap-2"><span className="eyebrow">Minutes / session — {mins}</span>
          <input type="range" min={15} max={120} step={5} value={mins} onChange={(e) => setMins(+e.target.value)} /></label>
      </div>
    </Sheet>
  );
}

// ── Add injury sheet ─────────────────────────────────────
function AddInjury({ userId, onClose, onDone }: { userId: number; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [bodyPart, setBodyPart] = useState("");
  const [severity, setSeverity] = useState<Injury["severity"]>("moderate");
  const [days, setDays] = useState(21);
  const [restrict, setRestrict] = useState(true);

  const create = useMutation({
    mutationFn: () => api.addInjury(userId, {
      body_part: bodyPart.trim(),
      severity,
      recovery_expectation_days: days,
      pain_type: "dull_stiff",
      restricted_force_directions_json: restrict ? JSON.stringify(["against_gravity"]) : null,
    }),
    onSuccess: () => { toast("Injury added — plans will adapt"); onDone(); },
    onError: (e: Error) => toast(e.message, "err"),
  });

  return (
    <Sheet open onClose={onClose} title="Add an injury"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button disabled={!bodyPart.trim()} loading={create.isPending} onClick={() => create.mutate()}>Add</Button></>}>
      <div className="stack gap-4">
        <div className="stack gap-2">
          <span className="eyebrow">Where</span>
          <input className="vf-input" value={bodyPart} onChange={(e) => setBodyPart(e.target.value)} placeholder="right shoulder" list="bodyparts" />
          <datalist id="bodyparts">{BODY_PARTS.map((b) => <option key={b} value={b} />)}</datalist>
        </div>
        <div className="stack gap-2"><span className="eyebrow">Severity</span>
          <div className="row gap-2">
            {(["mild", "moderate", "severe"] as const).map((sv) => (
              <button key={sv} className={`vf-chip ${severity === sv ? "on" : ""}`} onClick={() => setSeverity(sv)}>{titleCase(sv)}</button>
            ))}
          </div>
        </div>
        <label className="stack gap-2"><span className="eyebrow">Expected recovery — {days} days</span>
          <input type="range" min={3} max={120} value={days} onChange={(e) => setDays(+e.target.value)} /></label>
        <label className="row gap-2" style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>
          <input type="checkbox" checked={restrict} onChange={(e) => setRestrict(e.target.checked)} />
          Avoid bodyweight / overhead loading on this area
        </label>
      </div>
    </Sheet>
  );
}
