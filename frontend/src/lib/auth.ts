/**
 * ==============================================================================
 * CLIENT TOKEN STORAGE + REFRESH COORDINATION (Phase 2J)
 * ==============================================================================
 *
 * The single place the client reads or writes JWTs. Storage is unchanged —
 * still `localStorage`, still the same keys — because moving tokens to
 * httpOnly cookies needs backend work and is deliberately not this phase.
 *
 * This module must not import React or AuthContext: `api.ts`, `admin-api.ts`
 * and the contexts all depend on it, so a dependency back into the component
 * tree would be a cycle. A failed refresh therefore reports through the
 * `onAuthCleared` subscription below, which `AuthProvider` listens to and
 * answers with its existing `logout()`.
 *
 * Per the Master Prompt (§10, §28) the backend has no logout or token
 * revocation endpoint, so clearing tokens client-side is all "logging out"
 * can mean here. Nothing in this file pretends otherwise.
 */

/** Canonical keys. Written by every login path and by a successful refresh. */
const TOKEN_KEY = "minishop_token";
const REFRESH_KEY = "minishop_refresh_token";

/**
 * Legacy access-token keys earlier builds wrote. Kept as read fallbacks so an
 * existing session is not silently signed out by an upgrade, and listed once
 * here rather than re-spelled in each caller — `CartContext` used to carry its
 * own byte-identical copy of this list.
 */
const LEGACY_TOKEN_KEYS = ["token", "access_token"] as const;

/**
 * Reads the stored JWT access token, newest key first, then the legacy
 * fallbacks. Returns null during SSR, where there is no localStorage.
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const current = localStorage.getItem(TOKEN_KEY);
  if (current) return current;
  for (const key of LEGACY_TOKEN_KEYS) {
    const legacy = localStorage.getItem(key);
    if (legacy) return legacy;
  }
  return null;
}

/** Reads the stored refresh token. Null during SSR or when absent. */
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

/**
 * Persists a token pair under the canonical keys.
 *
 * `ROTATE_REFRESH_TOKENS` is on server-side (`config/settings/base.py`), so
 * both `/api/auth/token/` and `/api/auth/token/refresh/` return a fresh
 * refresh token and both must be stored — keeping the old one would shorten
 * the session to the original refresh token's 7-day window.
 */
export function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

/**
 * Removes every stored token, legacy keys included.
 *
 * The legacy keys have to go too: `getAuthToken()` falls back to them, so
 * clearing only the canonical key could leave a stale legacy token that the
 * next read would hand straight back — the request would 401 again, and a
 * cleared session would look authenticated. The guest cart
 * (`minishop-cart`) is a different key and is deliberately untouched.
 */
export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  for (const key of LEGACY_TOKEN_KEYS) {
    localStorage.removeItem(key);
  }
}

// ---------------------------------------------------------------------------
// Auth-cleared notification
// ---------------------------------------------------------------------------

type AuthClearedListener = () => void;

const authClearedListeners = new Set<AuthClearedListener>();

/**
 * Subscribes to "the client session was cleared because a refresh failed".
 * Returns an unsubscribe function, so a React effect can clean up on unmount.
 */
export function onAuthCleared(listener: AuthClearedListener): () => void {
  authClearedListeners.add(listener);
  return () => {
    authClearedListeners.delete(listener);
  };
}

function notifyAuthCleared(): void {
  // A throwing listener must not turn a failed refresh into an unhandled
  // rejection inside whichever request happened to trigger it.
  authClearedListeners.forEach((listener) => {
    try {
      listener();
    } catch {
      /* a subscriber's failure is not the refresh's problem */
    }
  });
}

// ---------------------------------------------------------------------------
// Single-flight refresh
// ---------------------------------------------------------------------------

/**
 * The refresh in progress, if any. Module-level on purpose: both API layers
 * import this module, so they share one coordinator rather than one each.
 */
let inFlightRefresh: Promise<string | null> | null = null;

/**
 * Refreshes the access token at most once per burst of 401s.
 *
 * The first caller starts the request and publishes its promise; every caller
 * that arrives while it is pending awaits that same promise and receives the
 * same token, so N simultaneous 401s produce exactly one
 * `POST /api/auth/token/refresh/`. This matters beyond saving requests:
 * `ROTATE_REFRESH_TOKENS` is on, so N parallel refreshes would each mint a
 * different refresh token and race on the write, leaving whichever lost the
 * race orphaned. (`BLACKLIST_AFTER_ROTATION` is currently off, so they would
 * all still succeed today — single-flight is what keeps that from becoming a
 * silent session loss if blacklisting is ever turned on.)
 *
 * Resolves to the new access token, or to null when the session is gone — in
 * which case the tokens have already been cleared and `onAuthCleared`
 * subscribers have already been notified. A null result means "do not retry".
 */
export function refreshTokenOnce(): Promise<string | null> {
  if (inFlightRefresh) return inFlightRefresh;

  inFlightRefresh = performRefresh().finally(() => {
    inFlightRefresh = null;
  });

  return inFlightRefresh;
}

async function performRefresh(): Promise<string | null> {
  const refresh = getRefreshToken();

  if (!refresh) {
    // Nothing to refresh with. Treat it as a failed refresh, but without
    // spending a request to be told so.
    failRefresh();
    return null;
  }

  try {
    // Imported lazily to keep `api.ts` -> `auth.ts` a one-way static
    // dependency. `refreshAccessToken` is reused exactly as it is rather than
    // the refresh request being reimplemented here, and because it is a plain
    // `fetch` it can never re-enter the 401 interceptor that calls this.
    const { refreshAccessToken } = await import("./api");
    const tokens = await refreshAccessToken(refresh);
    setTokens(tokens.access, tokens.refresh);
    return tokens.access;
  } catch {
    failRefresh();
    return null;
  }
}

function failRefresh(): void {
  clearTokens();
  notifyAuthCleared();
}
