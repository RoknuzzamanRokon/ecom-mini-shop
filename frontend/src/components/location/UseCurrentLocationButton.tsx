"use client";

import React, { useState } from "react";
import {
  CurrentPosition,
  GeolocationError,
  LOW_ACCURACY_METERS,
  formatAccuracy,
  getCurrentPosition,
  isValidCoordinatePair,
  openStreetMapUrl,
  roundCoordinate,
  toGeolocationError,
} from "@/lib/geolocation";

type LocateState =
  | { kind: "idle" }
  | { kind: "locating" }
  | { kind: "found"; accuracy: number }
  | { kind: "failed"; error: GeolocationError };

interface UseCurrentLocationButtonProps {
  /** Receives the reading with latitude/longitude rounded to 7 decimal places. */
  onLocated: (position: CurrentPosition) => void;
  disabled?: boolean;
}

/**
 * "Use My Current Location" for forms that take a latitude/longitude pair.
 * It only fills the form: the user still reviews the numbers, can type them by
 * hand instead, and the backend validates whatever is submitted.
 */
export default function UseCurrentLocationButton({
  onLocated,
  disabled = false,
}: UseCurrentLocationButtonProps) {
  const [state, setState] = useState<LocateState>({ kind: "idle" });
  const locating = state.kind === "locating";

  const locate = async () => {
    setState({ kind: "locating" });
    try {
      // maximumAge 0: a shop's saved location should never come from a cache.
      const position = await getCurrentPosition({ maximumAge: 0 });
      onLocated({
        ...position,
        latitude: roundCoordinate(position.latitude),
        longitude: roundCoordinate(position.longitude),
      });
      setState({ kind: "found", accuracy: position.accuracy });
    } catch (err) {
      setState({ kind: "failed", error: toGeolocationError(err) });
    }
  };

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={locate}
        disabled={disabled || locating}
        className="self-start inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <span
          aria-hidden="true"
          className={`material-symbols-outlined text-[16px] text-primary ${locating ? "animate-spin" : ""}`}
        >
          {locating ? "progress_activity" : "my_location"}
        </span>
        {locating ? "Locating…" : "Use My Current Location"}
      </button>

      <p role="status" aria-live="polite" className="text-[11px] leading-snug">
        {state.kind === "found" &&
          (state.accuracy > LOW_ACCURACY_METERS ? (
            <span className="mt-1.5 flex items-start gap-1 text-ink-body">
              <span aria-hidden="true" className="material-symbols-outlined text-[14px] text-accent">
                warning
              </span>
              <span>
                Location filled in, but it is only accurate to {formatAccuracy(state.accuracy)} —
                probably a network estimate. Check the point on the map, or type exact
                coordinates.
              </span>
            </span>
          ) : (
            <span className="mt-1.5 flex items-start gap-1 font-semibold text-success">
              <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                check_circle
              </span>
              <span>
                Location filled in ({formatAccuracy(state.accuracy)}). Check the coordinates
                before saving.
              </span>
            </span>
          ))}
        {state.kind === "failed" && (
          <span className="mt-1.5 flex items-start gap-1 font-semibold text-danger">
            <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
              location_off
            </span>
            <span>
              {state.error.message}{" "}
              {!state.error.retryable && "You can still type the coordinates."}
            </span>
          </span>
        )}
      </p>
    </div>
  );
}

/**
 * "Check on map" link for a latitude/longitude pair held as form strings.
 * Renders nothing until both hold a point the backend would accept.
 */
export function CoordinateMapLink({ latitude, longitude }: { latitude: string; longitude: string }) {
  if (latitude.trim() === "" || longitude.trim() === "") return null;
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (!isValidCoordinatePair(lat, lng)) return null;

  return (
    <a
      href={openStreetMapUrl(lat, lng)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
        map
      </span>
      Check on map
      <span className="sr-only">(opens OpenStreetMap in a new tab)</span>
    </a>
  );
}
