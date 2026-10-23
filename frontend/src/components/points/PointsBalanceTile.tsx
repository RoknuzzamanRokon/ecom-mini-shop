"use client";

import React, { useId } from "react";
import { formatCount } from "@/lib/admin-format";

export interface PointsBalanceTileProps {
  /** Null while it is still unknown (loading, or the request failed). */
  balance: number | null;
  loading?: boolean;
  /** Shown instead of the number when the balance could not be loaded. */
  error?: string | null;
  onRetry?: () => void;
  label?: string;
  /** One line under the number: what the points are for. */
  caption?: React.ReactNode;
  /** A link in the tile's top-right corner, e.g. to the full wallet. */
  headerAction?: React.ReactNode;
  /** Extra content under the caption, such as a low-balance note or buttons. */
  children?: React.ReactNode;
  className?: string;
}

/**
 * The "Available points" headline on a profile hero.
 *
 * It is drawn on the nav tokens, which every palette keeps dark in both light
 * and dark mode, so the balance reads as the one dark tile on the page whatever
 * theme is active. Points are not money, so this never shows ৳.
 */
export default function PointsBalanceTile({
  balance,
  loading = false,
  error = null,
  onRetry,
  label = "Available points",
  caption,
  headerAction,
  children,
  className = "",
}: PointsBalanceTileProps) {
  const labelId = useId();
  const isEmpty = !loading && !error && (balance ?? 0) === 0;

  return (
    <section
      aria-labelledby={labelId}
      aria-busy={loading || undefined}
      className={`relative isolate overflow-hidden rounded-2xl border border-accent/25 bg-linear-to-br from-nav to-nav-strip text-nav-active-text p-5 sm:p-6 flex flex-col gap-3 min-w-0 shadow-sm ${className}`}
    >
      {/* Decorative coin. */}
      <span
        aria-hidden="true"
        className="material-symbols-outlined pointer-events-none absolute -right-5 -bottom-8 -z-10 text-accent opacity-15 select-none text-[132px]"
      >
        toll
      </span>

      <div className="flex items-center justify-between gap-3">
        <h2
          id={labelId}
          className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-wider text-nav-text"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-accent text-[18px]">
            toll
          </span>
          {label}
        </h2>
        {headerAction}
      </div>

      {loading ? (
        <div className="h-10 w-32 rounded-lg bg-nav-active-text/10 animate-pulse" role="status">
          <span className="sr-only">Loading points…</span>
        </div>
      ) : error ? (
        <div className="space-y-2" role="alert">
          <p className="text-sm font-bold">Couldn&apos;t load your points.</p>
          <p className="text-xs text-nav-text break-words">{error}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 min-h-9 px-3 rounded-lg border border-nav-text/40 text-xs font-bold hover:bg-nav-active-text/10 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                refresh
              </span>
              Try again
            </button>
          )}
        </div>
      ) : (
        <p className="flex items-baseline gap-2 leading-none">
          <span
            className={`text-4xl sm:text-5xl font-black tracking-tight tabular-nums ${
              isEmpty ? "text-nav-text" : ""
            }`}
          >
            {formatCount(balance ?? 0)}
          </span>
          <span className="text-sm font-extrabold text-accent">pts</span>
        </p>
      )}

      {caption && !error && <p className="text-xs leading-relaxed text-nav-text">{caption}</p>}
      {children}
    </section>
  );
}

/** Button styles for actions placed inside the tile. */
export const POINTS_TILE_PRIMARY_ACTION =
  "inline-flex items-center justify-center gap-1.5 min-h-10 px-4 rounded-lg bg-accent hover:bg-accent-hover text-on-accent text-xs font-extrabold uppercase tracking-wider transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export const POINTS_TILE_SECONDARY_ACTION =
  "inline-flex items-center justify-center gap-1.5 min-h-10 px-4 rounded-lg border border-nav-text/40 text-nav-active-text hover:bg-nav-active-text/10 text-xs font-extrabold uppercase tracking-wider transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export const POINTS_TILE_HEADER_LINK =
  "inline-flex items-center gap-1 rounded-md text-[11px] font-bold text-nav-text hover:text-nav-active-text transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
