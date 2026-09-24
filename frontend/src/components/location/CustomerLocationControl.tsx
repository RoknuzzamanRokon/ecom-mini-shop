"use client";

import React from "react";
import { useCustomerLocation } from "@/context/LocationContext";
import { formatAccuracy } from "@/lib/geolocation";

interface CustomerLocationControlProps {
  /**
   * Show the "Use My Current Location" / "Try again" buttons while there is no
   * position. Pages whose body already offers those can turn them off here.
   */
  showStartActions?: boolean;
}

const SECONDARY_BUTTON =
  "inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

/**
 * The customer's location state in one line (off / locating / on / failed),
 * with the matching actions. Reads and drives LocationContext.
 */
export default function CustomerLocationControl({
  showStartActions = true,
}: CustomerLocationControlProps) {
  const { status, position, error, requestLocation, clearLocation } = useCustomerLocation();
  const locating = status === "locating";

  let icon = "location_searching";
  let tone = "bg-primary/10 text-primary";
  let title = "Location is off";
  let detail = "Share your location to see shops near you. It's only used for this search and isn't saved.";

  if (locating) {
    icon = "progress_activity";
    title = "Finding your location…";
    detail = "Your browser may ask for permission.";
  } else if (position) {
    icon = "my_location";
    tone = "bg-success/15 text-success";
    title = "Using your current location";
    detail = error
      ? `Couldn't refresh it: ${error.message}`
      : `Accurate to ${formatAccuracy(position.accuracy)}. Not saved anywhere.`;
  } else if (error) {
    icon = "location_off";
    tone = "bg-danger/10 text-danger";
    title = "Location unavailable";
    detail = error.message;
  }

  // Retrying can't help when the browser or the page itself can't do geolocation.
  const canRetry = error !== null && error.kind !== "unsupported" && error.kind !== "insecure";

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 min-w-0">
      <div className="flex items-start gap-2.5 min-w-0 flex-1">
        <span
          aria-hidden="true"
          className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${tone}`}
        >
          <span className={`material-symbols-outlined text-[20px] ${locating ? "animate-spin" : ""}`}>
            {icon}
          </span>
        </span>
        <div role="status" aria-live="polite" className="min-w-0">
          <p className="text-sm font-bold text-ink">{title}</p>
          <p className="text-xs text-ink-muted leading-snug">{detail}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 shrink-0">
        {position ? (
          <>
            <button
              type="button"
              onClick={() => requestLocation()}
              disabled={locating}
              className={SECONDARY_BUTTON}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Update location
            </button>
            <button
              type="button"
              onClick={clearLocation}
              disabled={locating}
              className={SECONDARY_BUTTON}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                location_off
              </span>
              Clear
            </button>
          </>
        ) : (
          showStartActions &&
          !locating &&
          (error === null || canRetry) && (
            <button type="button" onClick={() => requestLocation()} className={PRIMARY_BUTTON}>
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                {error ? "refresh" : "my_location"}
              </span>
              {error ? "Try again" : "Use My Current Location"}
            </button>
          )
        )}
      </div>
    </div>
  );
}
