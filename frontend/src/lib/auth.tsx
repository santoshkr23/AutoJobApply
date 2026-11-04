"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, type User } from "@/lib/api";

type Ctx = { user: User | null; loading: boolean; refresh: () => Promise<User | null>; logout: () => Promise<void> };
const AuthContext = createContext<Ctx>({ user: null, loading: true, refresh: async () => null, logout: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const u = await api<User>("/me");
      setUser(u);
      return u;
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) console.error(e);
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const logout = useCallback(async () => {
    try { await api("/auth/logout", { method: "POST" }); } finally { setUser(null); window.location.href = "/"; }
  }, []);

  return <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
