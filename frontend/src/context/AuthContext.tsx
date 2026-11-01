"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";
import { AuthUser } from "@/lib/types";
import { loginUser, getCurrentUser, revokeRefreshToken } from "@/lib/api";
import StartingPasswordScreen from "@/components/auth/StartingPasswordScreen";
import {
  clearTokens,
  getAuthToken,
  getRefreshToken,
  isTransientAuthFailure,
  onAuthCleared,
  setTokens,
} from "@/lib/auth";

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /**
   * Set when the stored session could not be checked because the server was
   * unreachable; the tokens are kept and `retrySession` tries again.
   */
  sessionError: string | null;
  retrySession: () => void;
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
  const [sessionError, setSessionError] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // Restore session on mount
  // -----------------------------------------------------------------------
  // An expired access token is renewed inside getCurrentUser: customerRequest
  // answers a 401 with the shared single-flight refreshTokenOnce(), which
  // clears the tokens itself when the server refuses them. So a failure here
  // is either "signed out" (clear what is left) or an outage, which keeps the
  // tokens and offers a retry instead of logging the user out (BUG-031).
  // State is only set in the promise callbacks.
  const initialize = useCallback((): Promise<void> => {
    const token = getAuthToken();
    if (!token) return Promise.resolve().then(() => setIsLoading(false));

    return getCurrentUser(token)
      .then((userData) => {
        setUser(userData);
        setSessionError(null);
      })
      .catch((err: unknown) => {
        setUser(null);
        if (isTransientAuthFailure(err)) {
          setSessionError(
            err instanceof Error && err.message && !(err instanceof TypeError)
              ? err.message
              : "The server could not be reached to restore your session."
          );
        } else {
          clearTokens();
          setSessionError(null);
        }
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  const retrySession = useCallback(() => {
    setIsLoading(true);
    initialize();
  }, [initialize]);

  // Coming back online is a good moment to try again by itself.
  useEffect(() => {
    if (!sessionError) return;
    const onOnline = () => retrySession();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [sessionError, retrySession]);

  // -----------------------------------------------------------------------
  // Login
  // -----------------------------------------------------------------------
  const login = useCallback(async (username: string, password: string) => {
    const tokens = await loginUser(username, password);
    setTokens(tokens.access, tokens.refresh);

    try {
      const userData = await getCurrentUser(tokens.access);
      setUser(userData);
      setSessionError(null);
    } catch (err) {
      // No half-signed-in state: tokens stored while the UI shows "Login"
      // would send cart calls to an account the user cannot see (BUG-092).
      clearTokens();
      throw err;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Logout — clears auth tokens but does NOT touch the guest cart
  // (guest cart uses a different localStorage key: "minishop-cart").
  // The refresh token is also revoked server-side, without waiting on it.
  // After a failed refresh (onAuthCleared below) the tokens are already
  // gone, so there is nothing to revoke.
  // -----------------------------------------------------------------------
  const logout = useCallback(() => {
    const refresh = getRefreshToken();
    clearTokens();
    setUser(null);
    setSessionError(null);
    if (refresh) void revokeRefreshToken(refresh);
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

  // -----------------------------------------------------------------------
  // Starting password: a Sales Team member set it when opening the account,
  // and the API answers nothing but the change until the owner replaces it
  // (rbac.StartingPassword). The new pair is unmarked.
  // -----------------------------------------------------------------------
  const finishPasswordChange = useCallback((tokens: { access: string; refresh: string }) => {
    setTokens(tokens.access, tokens.refresh);
    return getCurrentUser(tokens.access).then((userData) => setUser(userData));
  }, []);

  const isAuthenticated = user !== null;

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, isLoading, sessionError, retrySession, login, logout }}
    >
      {user?.must_change_password ? (
        <StartingPasswordScreen username={user.username} onChanged={finishPasswordChange} onSignOut={logout} />
      ) : (
        children
      )}
      {sessionError && !isLoading && (
        <div
          role="alert"
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] w-[calc(100%-2rem)] max-w-md p-3.5 rounded-xl bg-surface border border-accent/40 shadow-lg text-xs text-ink flex items-center gap-3"
        >
          <span className="material-symbols-outlined text-[20px] text-accent shrink-0">cloud_off</span>
          <span className="flex-1">{sessionError} Your sign-in is kept; retry once the connection is back.</span>
          <button
            type="button"
            onClick={retrySession}
            className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold uppercase tracking-wider cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}
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
