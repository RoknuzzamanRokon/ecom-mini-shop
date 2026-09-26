"use client";

import React, { useState } from "react";
import {
  NEARBY_MAX_RADIUS_KM,
  NEARBY_MIN_RADIUS_KM,
  NEARBY_RADIUS_OPTIONS,
  formatNearbyRadius,
  normalizeNearbyRadius,
} from "@/lib/api";

interface NearbyRadiusPickerProps {
  value: number;
  onChange: (radiusKm: number) => void;
}

const RANGE_TEXT = `${NEARBY_MIN_RADIUS_KM} to ${NEARBY_MAX_RADIUS_KM} km`;

/**
 * Radius chips (500 m – 50 km) plus a custom box for any radius from 100 m to
 * 50 km. The chips scroll sideways on narrow screens instead of wrapping.
 */
export default function NearbyRadiusPicker({ value, onChange }: NearbyRadiusPickerProps) {
  const isPreset = (NEARBY_RADIUS_OPTIONS as readonly number[]).includes(value);

  return (
    <fieldset className="min-w-0">
      <legend className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5">
        Search radius
      </legend>
      <div className="flex flex-col sm:flex-row sm:items-start gap-2">
        <div className="flex gap-1.5 overflow-x-auto p-0.5 -m-0.5 min-w-0">
          {NEARBY_RADIUS_OPTIONS.map((km) => {
            const active = km === value;
            return (
              <button
                key={km}
                type="button"
                aria-pressed={active}
                onClick={() => onChange(km)}
                className={`shrink-0 min-w-13 px-3 py-2 rounded-lg border text-xs font-bold whitespace-nowrap transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                  active
                    ? "bg-primary border-primary text-on-primary shadow-xs"
                    : "bg-surface border-line text-ink hover:bg-surface-alt"
                }`}
              >
                {formatNearbyRadius(km)}
              </button>
            );
          })}
        </div>
        {/* Keyed on the radius so the box shows the URL's value again after back/forward. */}
        <CustomRadius key={value} value={value} active={!isPreset} onChange={onChange} />
      </div>
    </fieldset>
  );
}

/** "Custom ___ km [Set]": any radius in range, rounded to 10 m. */
function CustomRadius({
  value,
  active,
  onChange,
}: {
  value: number;
  active: boolean;
  onChange: (radiusKm: number) => void;
}) {
  const [draft, setDraft] = useState(active ? String(value) : "");
  const [invalid, setInvalid] = useState(false);

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        const km = normalizeNearbyRadius(draft.trim());
        if (km === null) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        if (km !== value) onChange(km);
      }}
      className="flex flex-col gap-1 shrink-0"
    >
      <div className="flex items-center gap-1.5">
        <label htmlFor="nearby-custom-radius" className="sr-only">
          Custom radius in kilometres, {RANGE_TEXT}
        </label>
        <div className="relative">
          <input
            id="nearby-custom-radius"
            type="number"
            inputMode="decimal"
            step="any"
            min={NEARBY_MIN_RADIUS_KM}
            max={NEARBY_MAX_RADIUS_KM}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              if (invalid) setInvalid(false);
            }}
            placeholder="Custom"
            aria-invalid={invalid}
            aria-describedby={invalid ? "nearby-custom-radius-error" : undefined}
            className={`w-24 rounded-lg border bg-surface py-2 pl-3 pr-8 text-xs font-bold text-ink placeholder:font-semibold placeholder-ink-faint [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none focus:outline-hidden focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
              invalid
                ? "border-danger"
                : active
                  ? "border-primary ring-2 ring-primary/25"
                  : "border-line"
            }`}
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] font-bold text-ink-muted"
          >
            km
          </span>
        </div>
        <button
          type="submit"
          className="shrink-0 px-3 py-2 rounded-lg border border-line bg-surface-alt hover:bg-surface-sunken text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Set
          <span className="sr-only"> custom radius</span>
        </button>
      </div>
      {invalid && (
        <p id="nearby-custom-radius-error" role="alert" className="text-[11px] font-semibold text-danger">
          Enter {RANGE_TEXT}, e.g. 0.3
        </p>
      )}
    </form>
  );
}
