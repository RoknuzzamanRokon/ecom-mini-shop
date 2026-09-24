"use client";

import React from "react";
import { NEARBY_RADIUS_OPTIONS } from "@/lib/api";

interface NearbyRadiusPickerProps {
  value: number;
  onChange: (radiusKm: number) => void;
}

/** Radius chips (1–50 km). Scrolls sideways on narrow screens instead of wrapping. */
export default function NearbyRadiusPicker({ value, onChange }: NearbyRadiusPickerProps) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5">
        Search radius
      </legend>
      <div className="flex gap-1.5 overflow-x-auto p-0.5 -m-0.5">
        {NEARBY_RADIUS_OPTIONS.map((km) => {
          const active = km === value;
          return (
            <button
              key={km}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(km)}
              className={`shrink-0 min-w-13 px-3 py-2 rounded-lg border text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                active
                  ? "bg-primary border-primary text-on-primary shadow-xs"
                  : "bg-surface border-line text-ink hover:bg-surface-alt"
              }`}
            >
              {km} km
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
