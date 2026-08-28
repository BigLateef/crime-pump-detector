"use client";

import { createContext, useContext, useEffect, useState, useRef, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, setUnauthorizedHandler } from "./api";
import { clearTokens, getAccessToken, setTokens } from "./auth";
import { isAuthPage, safeNextPath } from "./authRedirect";
import { UserOut } from "./types";

interface AuthContextValue {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string, next?: string | null) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  // Guards against firing more than one redirect for one dead session -
  // e.g. three components each get a 401 from the same expired token in
  // the same render pass.
  const redirectingRef = useRef(false);

  async function refreshUser() {
    if (!getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await apiFetch<UserOut>("/auth/me");
      setUser(me);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearTokens();
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshUser();

    setUnauthorizedHandler((currentPath: string) => {
      setUser(null);
      if (redirectingRef.current) return;
      if (isAuthPage(currentPath)) return; // already on a public auth page - nothing to do
      redirectingRef.current = true;
      const next = encodeURIComponent(currentPath);
      router.push(`/login?next=${next}`);
      // Released on the next tick rather than immediately: React state
      // updates and the navigation itself are async, so releasing too
      // early could let a second in-flight request's 401 re-trigger a
      // redirect before the first one has actually navigated away.
      setTimeout(() => {
        redirectingRef.current = false;
      }, 1000);
    });

    return () => setUnauthorizedHandler(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(email: string, password: string, next?: string | null) {
    const data = await apiFetch<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setTokens(data.access_token, data.refresh_token);
    await refreshUser();
    router.push(safeNextPath(next ?? null));
  }

  function logout() {
    clearTokens();
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
