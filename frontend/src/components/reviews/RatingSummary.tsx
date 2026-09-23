import React from "react";
import StarRating from "@/components/reviews/StarRating";
import { RatingBreakdown } from "@/lib/types";

interface RatingSummaryProps {
  average: number;
  count: number;
  /** Optional: without it only the average and count are shown. */
  breakdown?: RatingBreakdown;
}

const STAR_LEVELS = ["5", "4", "3", "2", "1"] as const;

/**
 * Review summary: large average + stars + count, and one bar per star level
 * showing its share of all reviews.
 */
export default function RatingSummary({ average, count, breakdown }: RatingSummaryProps) {
  // Percentages come from the breakdown itself, so the bars always add up even
  // if `count` and `breakdown` were fetched a moment apart.
  const breakdownTotal = breakdown
    ? STAR_LEVELS.reduce((sum, level) => sum + (breakdown[level] ?? 0), 0)
    : 0;

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-5 sm:gap-8">
      <div className="flex flex-col items-center sm:items-start shrink-0">
        <span className="text-4xl font-extrabold text-ink leading-none tabular-nums">
          {average.toFixed(1)}
        </span>
        <StarRating rating={average} size={18} className="mt-2" />
        <span className="text-xs text-ink-muted mt-1.5">
          {count} review{count === 1 ? "" : "s"}
        </span>
      </div>

      {breakdown && breakdownTotal > 0 && (
        <ul className="flex-1 min-w-0 space-y-1.5">
          {STAR_LEVELS.map((level) => {
            const n = breakdown[level] ?? 0;
            const percent = Math.round((n / breakdownTotal) * 100);
            return (
              <li key={level} className="flex items-center gap-2 text-xs">
                <span className="w-7 shrink-0 flex items-center gap-0.5 font-semibold text-ink-body">
                  {level}
                  <span
                    aria-hidden="true"
                    className="material-symbols-outlined fill-active text-star leading-none"
                    style={{ fontSize: 12 }}
                  >
                    star
                  </span>
                </span>
                <div
                  role="img"
                  aria-label={`${percent}% of reviews gave ${level} star${level === "1" ? "" : "s"}`}
                  className="flex-1 h-2 rounded-full bg-surface-sunken overflow-hidden"
                >
                  <div className="h-full rounded-full bg-star" style={{ width: `${percent}%` }} />
                </div>
                <span className="w-9 shrink-0 text-right text-ink-muted tabular-nums">
                  {percent}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
