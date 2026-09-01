import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { User } from "../lib/types";

const KEY = "vectorfit.userId";

interface Ctx {
  userId: number | null;
  user: User | undefined;
  isLoading: boolean;
  error: unknown;
  setUserId: (id: number) => void;
  clearUser: () => void;
}

const UserCtx = createContext<Ctx | null>(null);

function readInitial(): number | null {
  // deep-link override: ?as=<id> (handy for demos / sharing a profile)
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("as");
    if (fromUrl && Number(fromUrl)) {
      localStorage.setItem(KEY, fromUrl);
      return Number(fromUrl);
    }
  } catch { /* */ }
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? Number(raw) || null : null;
  } catch {
    return null;
  }
}

export function UserProvider({ children }: { children: ReactNode }) {
  const [userId, setId] = useState<number | null>(readInitial);

  const { data: user, isLoading, error } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => api.getUser(userId as number),
    enabled: userId != null,
    retry: 1,
  });

  const setUserId = useCallback((id: number) => {
    try { localStorage.setItem(KEY, String(id)); } catch { /* private mode */ }
    setId(id);
  }, []);

  const clearUser = useCallback(() => {
    try { localStorage.removeItem(KEY); } catch { /* */ }
    setId(null);
  }, []);

  const value = useMemo<Ctx>(
    () => ({ userId, user, isLoading, error, setUserId, clearUser }),
    [userId, user, isLoading, error, setUserId, clearUser],
  );

  return <UserCtx.Provider value={value}>{children}</UserCtx.Provider>;
}

export function useUser() {
  const ctx = useContext(UserCtx);
  if (!ctx) throw new Error("useUser must be used inside <UserProvider>");
  return ctx;
}

/** Convenience for screens that require a chosen user — asserts non-null id. */
export function useUserId(): number {
  const { userId } = useUser();
  if (userId == null) throw new Error("No active user");
  return userId;
}
