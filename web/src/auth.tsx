import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore, type User } from "./api";

interface Session {
  user: User | null;
  permissions: Set<string>;
  loading: boolean;
  can: (perm: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<Session | null>(null);

export const ROLE_LABELS: Record<string, string> = {
  admin: "Administrateur",
  agent_sante: "Agent de santé",
  medecin: "Médecin",
  specialiste: "Spécialiste",
  responsable_sanitaire: "Responsable sanitaire",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
    setPermissions(new Set());
  }, []);

  const loadMe = useCallback(async () => {
    const me = await api.me();
    setUser(me.user);
    setPermissions(new Set(me.permissions));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    loadMe().catch(logout).finally(() => setLoading(false));
  }, [loadMe, logout]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    tokenStore.set(res.access_token);
    await loadMe();
  }, [loadMe]);

  const value = useMemo<Session>(() => ({
    user, permissions, loading, login, logout,
    can: (perm) => permissions.has(perm),
  }), [user, permissions, loading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Session {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans <AuthProvider>");
  return ctx;
}
