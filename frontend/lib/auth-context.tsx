"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type AuthResponse, type User } from "@/lib/api";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  signIn: (response: AuthResponse) => void;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthCtx>({
  user: null,
  loading: true,
  signIn: () => {},
  signOut: () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.get<User>("/api/auth/me"));
    } catch {
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load: Promise<User | null> = getToken()
      ? api.get<User>("/api/auth/me").catch(() => {
          setToken(null);
          return null;
        })
      : Promise.resolve(null);
    load.then((loadedUser) => {
      if (cancelled) return;
      setUser(loadedUser);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback((response: AuthResponse) => {
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, signIn, signOut, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
