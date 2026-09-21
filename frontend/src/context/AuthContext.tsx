"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { AuthUser } from "@/lib/types";
import { loginUser, refreshAccessToken, getCurrentUser } from "@/lib/api";
import {
  clearTokens,
  getAuthToken,
  getRefreshToken,
  onAuthCleared,
  setTokens,
} from "@/lib/auth";

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ---------------------------------------------------------------------------
// Token storage lives in lib/auth.ts (Phase 2J). The four private helpers that
// used to sit here — getStoredToken / getStoredRefresh / storeTokens /
// clearTokens — were one of four independent readers of the same localStorage
// keys; they now come from the one shared accessor that api.ts, admin-api.ts
// and CartContext also use. Storage mechanism and key names are unchanged.
// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // -----------------------------------------------------------------------
  // Restore session on mount
  // -----------------------------------------------------------------------
  const initialize = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      // Try the stored access token first
      const userData = await getCurrentUser(token);
      setUser(userData);
    } catch {
      // Access token may be expired — try refresh
      const refresh = getRefreshToken();
      if (refresh) {
        try {
          const tokens = await refreshAccessToken(refresh);
          setTokens(tokens.access, tokens.refresh);
          const userData = await getCurrentUser(tokens.access);
          setUser(userData);
        } catch {
          // Refresh also failed — clear everything silently
          clearTokens();
          setUser(null);
        }
      } else {
        clearTokens();
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  // -----------------------------------------------------------------------
  // Login
  // -----------------------------------------------------------------------
  const login = useCallback(async (username: string, password: string) => {
    const tokens = await loginUser(username, password);
    setTokens(tokens.access, tokens.refresh);

    const userData = await getCurrentUser(tokens.access);
    setUser(userData);
  }, []);

  // -----------------------------------------------------------------------
  // Logout — clears auth tokens but does NOT touch the guest cart
  // (guest cart uses a different localStorage key: "minishop-cart")
  // -----------------------------------------------------------------------
  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  // -----------------------------------------------------------------------
  // A mid-session refresh failure clears the tokens inside lib/auth.ts, which
  // has no access to this state. Without this subscription `isAuthenticated`
  // would stay true against a session that no longer exists, which is exactly
  // the "falsely authenticated" state Phase 2J exists to remove. The tokens
  // are already gone by the time this fires, so it only has to reset state —
  // calling `logout()` keeps that in one place.
  // -----------------------------------------------------------------------
  useEffect(() => onAuthCleared(logout), [logout]);

  const isAuthenticated = user !== null;

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, isLoading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
