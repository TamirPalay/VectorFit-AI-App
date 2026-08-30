import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useUser } from "./context/UserContext";
import { AppShell } from "./components/shell/AppShell";
import { Loader, ErrorState, Button } from "./components/ui/primitives";
import { Onboarding } from "./screens/Onboarding";
import { Today } from "./screens/Today";

const Plan = lazy(() => import("./screens/Plan").then((m) => ({ default: m.Plan })));
const Builder = lazy(() => import("./screens/Builder").then((m) => ({ default: m.Builder })));
const Activity = lazy(() => import("./screens/Activity").then((m) => ({ default: m.Activity })));
const Progress = lazy(() => import("./screens/Progress").then((m) => ({ default: m.Progress })));
const WorkoutDetail = lazy(() => import("./screens/WorkoutDetail").then((m) => ({ default: m.WorkoutDetail })));
const Profile = lazy(() => import("./screens/Profile").then((m) => ({ default: m.Profile })));

export function App() {
  const { userId, user, isLoading, error, clearUser } = useUser();

  if (userId == null) return <Onboarding />;

  if (isLoading) {
    return (
      <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
        <Loader label="Loading your profile…" />
      </div>
    );
  }

  if (error || !user) {
    return (
      <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: 24 }}>
        <div className="stack gap-4" style={{ maxWidth: 420 }}>
          <ErrorState error={error} />
          <Button variant="secondary" onClick={clearUser}>Choose a different profile</Button>
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      <Suspense fallback={<Loader />}>
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/plan/build" element={<Builder />} />
          <Route path="/plan/build/:workoutId" element={<Builder />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/progress" element={<Progress />} />
          <Route path="/progress/history" element={<Navigate to="/activity" replace />} />
          <Route path="/progress/workout/:logId" element={<WorkoutDetail />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
