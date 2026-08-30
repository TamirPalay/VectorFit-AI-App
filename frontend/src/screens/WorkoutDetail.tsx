import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useUser } from "../context/UserContext";
import { fmtDate } from "../lib/format";
import { Button, Loader, ErrorState, Pill } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { SessionRunner } from "../components/workout/SessionRunner";
import { ChevronLeft, Trash } from "../components/icons";

export function WorkoutDetail() {
  const { logId } = useParams();
  const lid = Number(logId);
  const { userId } = useUser();
  const id = userId as number;
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();

  const q = useQuery({ queryKey: ["log", id, lid], queryFn: () => api.log(id, lid) });

  const del = useMutation({
    mutationFn: () => api.deleteLog(id, lid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["logs", id] });
      qc.invalidateQueries({ queryKey: ["dash"] });
      toast("Deleted");
      nav(-1);
    },
  });

  if (q.isLoading) return <Loader />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;

  const log = q.data;

  return (
    <div className="screen">
      <button className="row gap-1 dim" onClick={() => nav(-1)} style={{ fontSize: "0.85rem" }}>
        <ChevronLeft width="1em" height="1em" /> Back
      </button>

      <div className="screen-head">
        <div className="row gap-2 wrap center">
          <h1 style={{ fontSize: "1.9rem" }}>{log.name || log.workout_label || "Workout"}</h1>
          <Pill token="plain">{log.source === "daily" ? "Daily plan" : "Custom"}</Pill>
          {log.completed_at ? <Pill token="good" dot>Done</Pill> : <Pill token="warn" dot>In progress</Pill>}
        </div>
        <p>{fmtDate(log.started_at, { weekday: "long", month: "long", day: "numeric" })}</p>
      </div>

      <SessionRunner
        log={log}
        userId={id}
        onChange={(updated) => qc.setQueryData(["log", id, lid], updated)}
      />

      <Button variant="danger" onClick={() => confirm("Delete this workout from your history?") && del.mutate()}>
        <Trash width="1em" height="1em" /> Delete
      </Button>
    </div>
  );
}
