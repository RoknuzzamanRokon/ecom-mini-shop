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

// ---------------------------------------------------------------------------
// Storage keys — `minishop_token` is intentionally the same key that
// CartContext.getAuthToken() already checks so cart becomes backend-aware
// automatically after login.
// ---------------------------------------------------------------------------
const TOKEN_KEY = "minishop_token";
const REFRESH_KEY = "minishop_refresh_token";

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

function getStoredRefresh(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

function storeTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

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
    const token = getStoredToken();
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
      const refresh = getStoredRefresh();
      if (refresh) {
        try {
          const tokens = await refreshAccessToken(refresh);
          storeTokens(tokens.access, tokens.refresh);
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
    storeTokens(tokens.access, tokens.refresh);

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
