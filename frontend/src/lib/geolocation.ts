/**
 * ==========================================================================
 * BROWSER GEOLOCATION
 * ==========================================================================
 *
 * The one place the app calls `navigator.geolocation`. Used by the "Use My
 * Current Location" button on the shop forms and by LocationContext for the
 * customer's nearby-shop search.
 *
 * Every failure becomes a `GeolocationError` with one of five kinds and a
 * fixed, user-facing message, so each caller shows the same words and never
 * has to know about `GeolocationPositionError` codes.
 *
 * Coordinates obtained here are only ever a convenience: the backend validates
 * every latitude/longitude/radius it receives.
 */

export type GeolocationErrorKind =
  | "unsupported"
  | "insecure"
  | "denied"
  | "unavailable"
  | "timeout";

export const GEOLOCATION_MESSAGES: Record<GeolocationErrorKind, string> = {
  unsupported: "Your browser can't share its location.",
  insecure: "Location only works on a secure (HTTPS) connection.",
  denied:
    "Location access is blocked. Allow it for this site in your browser settings, then try again.",
  unavailable: "Your location couldn't be determined. Check that location services are on, then try again.",
  timeout: "Finding your location took too long. Please try again.",
};

export class GeolocationError extends Error {
  kind: GeolocationErrorKind;

  constructor(kind: GeolocationErrorKind) {
    super(GEOLOCATION_MESSAGES[kind]);
    this.name = "GeolocationError";
    this.kind = kind;
  }

  /** Whether trying again (without changing browser settings) can succeed. */
  get retryable(): boolean {
    return this.kind === "unavailable" || this.kind === "timeout";
  }
}

export interface CurrentPosition {
  latitude: number;
  longitude: number;
  /** Radius of the 95% confidence circle, in metres. */
  accuracy: number;
  /** When the browser took the reading (ms since epoch). */
  timestamp: number;
}

/** Accuracy (metres) above which a reading is probably a Wi-Fi/IP estimate. */
export const LOW_ACCURACY_METERS = 500;

/**
 * `null` when geolocation can be requested here, otherwise the reason it can't.
 * Browsers only expose geolocation in a secure context (HTTPS, or localhost).
 */
export function geolocationBlocker(): GeolocationErrorKind | null {
  if (typeof window === "undefined" || typeof navigator === "undefined") return "unsupported";
  if (window.isSecureContext === false) return "insecure";
  if (!("geolocation" in navigator) || !navigator.geolocation) return "unsupported";
  return null;
}

export interface GetPositionOptions {
  /** How old a cached reading may be, in ms. 0 always asks for a fresh one. */
  maximumAge?: number;
  timeout?: number;
}

export function getCurrentPosition({
  maximumAge = 0,
  timeout = 15000,
}: GetPositionOptions = {}): Promise<CurrentPosition> {
  const blocker = geolocationBlocker();
  if (blocker) return Promise.reject(new GeolocationError(blocker));

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          timestamp: position.timestamp,
        }),
      (error) => {
        if (error.code === error.PERMISSION_DENIED) reject(new GeolocationError("denied"));
        else if (error.code === error.TIMEOUT) reject(new GeolocationError("timeout"));
        else reject(new GeolocationError("unavailable"));
      },
      { enableHighAccuracy: true, maximumAge, timeout }
    );
  });
}

/** Normalises anything thrown by `getCurrentPosition` into a GeolocationError. */
export function toGeolocationError(err: unknown): GeolocationError {
  return err instanceof GeolocationError ? err : new GeolocationError("unavailable");
}

/** 7 decimal places (~1 cm) — the precision the backend stores. */
export function roundCoordinate(value: number, digits = 7): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

/** A finite pair inside the ranges the backend accepts. */
export function isValidCoordinatePair(latitude: number, longitude: number): boolean {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

/** "±12 m" / "±1.4 km". */
export function formatAccuracy(meters: number): string {
  if (meters < 1000) return `±${Math.max(1, Math.round(meters))} m`;
  return `±${(meters / 1000).toFixed(1)} km`;
}

/** "850 m" / "1.2 km" / "15 km". */
export function formatDistance(km: number): string {
  if (km < 1) return `${Math.max(1, Math.round(km * 1000))} m`;
  if (km < 10) return `${km.toFixed(1)} km`;
  return `${Math.round(km)} km`;
}

/** openstreetmap.org link with a marker on the point, for checking coordinates. */
export function openStreetMapUrl(latitude: number, longitude: number, zoom = 17): string {
  const lat = roundCoordinate(latitude, 6);
  const lng = roundCoordinate(longitude, 6);
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=${zoom}/${lat}/${lng}`;
}
