"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CurrentPosition,
  GeolocationError,
  getCurrentPosition,
  toGeolocationError,
} from "@/lib/geolocation";

/**
 * The customer's current location, for nearby-shop search.
 *
 * Deliberately memory-only: nothing here is written to localStorage, the URL
 * or the backend. The location survives client-side navigation (home → nearby
 * shops → a shop page → back) because the provider sits in the root layout, and
 * is gone on reload or when the tab closes.
 *
 * Nothing asks the browser for the location on its own. `requestLocation()` is
 * called from a click, except that a page may call it on mount when
 * `permission` is already "granted" (no prompt is shown in that case).
 */

/** idle: never asked, or cleared · locating · ready: have a position · error: last attempt failed */
export type LocationStatus = "idle" | "locating" | "ready" | "error";

/** The Permissions API state, or "unknown" where the browser doesn't expose it. */
export type LocationPermission = "granted" | "denied" | "prompt" | "unknown";

interface LocationContextType {
  status: LocationStatus;
  /** The last good position. Kept when a refresh fails, so results can stay on screen. */
  position: CurrentPosition | null;
  /** Why the last attempt failed (null after a success or a clear). */
  error: GeolocationError | null;
  permission: LocationPermission;
  /** Resolves with the new position, or null on failure (see `error`). */
  requestLocation: () => Promise<CurrentPosition | null>;
  clearLocation: () => void;
}

const LocationContext = createContext<LocationContextType | undefined>(undefined);

// A reading up to a minute old is fine for "shops near me", and lets a second
// request (say, from another page) answer without waiting on the GPS again.
const CUSTOMER_MAXIMUM_AGE_MS = 60_000;

export function LocationProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<LocationStatus>("idle");
  const [position, setPosition] = useState<CurrentPosition | null>(null);
  const [error, setError] = useState<GeolocationError | null>(null);
  const [permission, setPermission] = useState<LocationPermission>("unknown");
  const inFlight = useRef<Promise<CurrentPosition | null> | null>(null);

  useEffect(() => {
    let permissionStatus: PermissionStatus | null = null;
    let cancelled = false;
    const sync = () => {
      if (permissionStatus) setPermission(permissionStatus.state as LocationPermission);
    };

    navigator.permissions
      ?.query({ name: "geolocation" })
      .then((result) => {
        if (cancelled) return;
        permissionStatus = result;
        sync();
        result.addEventListener("change", sync);
      })
      .catch(() => {
        // Older browsers: stay "unknown" and rely on the prompt.
      });

    return () => {
      cancelled = true;
      permissionStatus?.removeEventListener("change", sync);
    };
  }, []);

  const requestLocation = useCallback(() => {
    // Two quick clicks (or two components) share one browser request.
    if (inFlight.current) return inFlight.current;

    setStatus("locating");
    setError(null);
    const request = getCurrentPosition({ maximumAge: CUSTOMER_MAXIMUM_AGE_MS })
      .then((next) => {
        setPosition(next);
        setStatus("ready");
        setPermission("granted");
        return next;
      })
      .catch((err: unknown) => {
        const failure = toGeolocationError(err);
        setError(failure);
        setStatus("error");
        if (failure.kind === "denied") setPermission("denied");
        return null;
      })
      .finally(() => {
        inFlight.current = null;
      });

    inFlight.current = request;
    return request;
  }, []);

  const clearLocation = useCallback(() => {
    setPosition(null);
    setError(null);
    setStatus("idle");
  }, []);

  const value = useMemo(
    () => ({ status, position, error, permission, requestLocation, clearLocation }),
    [status, position, error, permission, requestLocation, clearLocation]
  );

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useCustomerLocation() {
  const context = useContext(LocationContext);
  if (context === undefined) {
    throw new Error("useCustomerLocation must be used within a LocationProvider");
  }
  return context;
}
