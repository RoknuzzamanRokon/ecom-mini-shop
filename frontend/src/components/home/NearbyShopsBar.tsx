"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import CustomerLocationControl from "@/components/location/CustomerLocationControl";
import { useCustomerLocation } from "@/context/LocationContext";
import { DEFAULT_NEARBY_RADIUS_KM, NEARBY_RADIUS_OPTIONS } from "@/lib/api";

/**
 * Home page entry to nearby-shop discovery. Separate from product search:
 * nothing here changes the catalogue below, and browsing never needs the
 * customer's location. "Find Nearby Shops" asks for it only when clicked.
 */
export default function NearbyShopsBar() {
  const router = useRouter();
  const { position, status, requestLocation } = useCustomerLocation();
  const [radius, setRadius] = useState<number>(DEFAULT_NEARBY_RADIUS_KM);
  const locating = status === "locating";

  const findNearby = async () => {
    // Without a location, ask first; on failure stay here, where the control
    // above now explains what went wrong.
    const located = position ?? (await requestLocation());
    if (located) router.push(`/shops/nearby?radius=${radius}`);
  };

  return (
    <section
      aria-labelledby="nearby-shops-bar-title"
      className="bg-surface border border-line rounded-2xl shadow-xs p-4 flex flex-col xl:flex-row xl:items-center gap-4"
    >
      <div className="flex-1 min-w-0">
        <h2
          id="nearby-shops-bar-title"
          className="mb-2 flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider text-accent"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
            near_me
          </span>
          Shops near you
        </h2>
        <CustomerLocationControl />
      </div>

      <div className="flex items-end gap-2 shrink-0 xl:pl-4 xl:border-l xl:border-line">
        <label className="flex flex-col flex-1 sm:flex-none min-w-0">
          <span className="mb-1 text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">
            Radius
          </span>
          <select
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            className="bg-surface-alt border border-line rounded-lg px-3 py-2 text-xs font-bold text-ink cursor-pointer focus:outline-hidden focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
          >
            {NEARBY_RADIUS_OPTIONS.map((km) => (
              <option key={km} value={km}>
                {km} km
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={findNearby}
          disabled={locating}
          className="shrink-0 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-on-accent text-xs font-bold transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            travel_explore
          </span>
          Find Nearby Shops
        </button>
      </div>
    </section>
  );
}
