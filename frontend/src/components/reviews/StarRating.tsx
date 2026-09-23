import React from "react";

interface StarRatingProps {
  /** Average or single rating on a 0–5 scale; fractional values are allowed. */
  rating: number;
  /** Icon size in pixels. */
  size?: number;
  className?: string;
}

/**
 * Read-only 5-star display, rounded to the nearest half star.
 *
 * A rating of 0 can only mean "no reviews yet" (the lowest real rating is 1),
 * so it renders as faint outlines instead of star-coloured ones.
 *
 * `star_half` must NOT get `fill-active`: at FILL 0 its left half is already
 * solid, which is exactly the half-star look.
 */
export default function StarRating({ rating, size = 14, className = "" }: StarRatingProps) {
  const safe = Number.isFinite(rating) ? Math.min(Math.max(rating, 0), 5) : 0;
  const halves = Math.round(safe * 2);
  const full = Math.floor(halves / 2);
  const hasHalf = halves % 2 === 1;
  const label = safe > 0 ? `Rated ${safe.toFixed(1)} out of 5` : "No ratings yet";

  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`inline-flex items-center shrink-0 ${safe > 0 ? "text-star" : "text-ink-faint"} ${className}`}
    >
      {[0, 1, 2, 3, 4].map((i) => {
        const isFull = i < full;
        const isHalf = !isFull && hasHalf && i === full;
        return (
          <span
            key={i}
            aria-hidden="true"
            className={`material-symbols-outlined leading-none ${isFull ? "fill-active" : ""}`}
            style={{ fontSize: size }}
          >
            {isHalf ? "star_half" : "star"}
          </span>
        );
      })}
    </span>
  );
}
