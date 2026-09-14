"use client";

import React from "react";

/**
 * Windowed pagination for management tables.
 *
 * Distinct from the storefront's components/home/Pagination, which renders every
 * page number — workable for a handful of product pages, but not for an audit log
 * with hundreds. This variant windows the page list with ellipses and reports the
 * visible record range, which management tables need.
 */
export interface AdminPaginationProps {
  /** 1-indexed current page. */
  page: number;
  /** Total record count from the paginated API response (`count`). */
  totalCount: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  /** Number of page links either side of the current page. */
  siblingCount?: number;
  className?: string;
}

const ELLIPSIS = "ellipsis" as const;
type PageToken = number | typeof ELLIPSIS;

/** Builds a windowed page list, e.g. [1, 'ellipsis', 7, 8, 9, 'ellipsis', 42]. */
function buildPageTokens(
  current: number,
  totalPages: number,
  siblingCount: number
): PageToken[] {
  // 2 edges + 2 ellipses + current + siblings either side
  const maxSlots = siblingCount * 2 + 5;
  if (totalPages <= maxSlots) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const left = Math.max(current - siblingCount, 1);
  const right = Math.min(current + siblingCount, totalPages);
  const showLeftEllipsis = left > 2;
  const showRightEllipsis = right < totalPages - 1;

  const tokens: PageToken[] = [1];
  if (showLeftEllipsis) tokens.push(ELLIPSIS);

  for (let p = Math.max(left, 2); p <= Math.min(right, totalPages - 1); p += 1) {
    tokens.push(p);
  }

  if (showRightEllipsis) tokens.push(ELLIPSIS);
  tokens.push(totalPages);
  return tokens;
}

export default function AdminPagination({
  page,
  totalCount,
  pageSize,
  onPageChange,
  disabled = false,
  siblingCount = 1,
  className = "",
}: AdminPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalCount / Math.max(1, pageSize)));
  const current = Math.min(Math.max(1, page), totalPages);

  if (totalCount === 0) return null;

  const firstRecord = (current - 1) * pageSize + 1;
  const lastRecord = Math.min(current * pageSize, totalCount);
  const tokens = buildPageTokens(current, totalPages, siblingCount);

  const go = (target: number) => {
    const clamped = Math.min(Math.max(1, target), totalPages);
    if (clamped !== current && !disabled) onPageChange(clamped);
  };

  const arrowClass =
    "w-8 h-8 rounded-lg border border-line bg-surface text-ink-muted hover:bg-surface-alt hover:text-ink flex items-center justify-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 mt-4 border-t border-line ${className}`}
    >
      <p className="text-[11px] text-ink-muted order-2 sm:order-1" aria-live="polite">
        Showing <span className="font-bold text-ink">{firstRecord}</span>–
        <span className="font-bold text-ink">{lastRecord}</span> of{" "}
        <span className="font-bold text-ink">{totalCount.toLocaleString("en-US")}</span>
      </p>

      <nav
        aria-label="Pagination"
        className="flex items-center gap-1.5 order-1 sm:order-2"
      >
        <button
          type="button"
          onClick={() => go(current - 1)}
          disabled={disabled || current <= 1}
          className={arrowClass}
          aria-label="Go to previous page"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            chevron_left
          </span>
        </button>

        {tokens.map((token, index) =>
          token === ELLIPSIS ? (
            <span
              // Ellipsis positions are stable for a given token list.
              key={`ellipsis-${index}`}
              aria-hidden="true"
              className="w-8 h-8 flex items-center justify-center text-ink-muted text-xs select-none"
            >
              …
            </span>
          ) : (
            <button
              key={token}
              type="button"
              onClick={() => go(token)}
              disabled={disabled}
              aria-label={`Go to page ${token}`}
              aria-current={token === current ? "page" : undefined}
              className={`w-8 h-8 rounded-lg text-xs font-bold flex items-center justify-center transition-colors cursor-pointer disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                token === current
                  ? "bg-primary text-on-primary shadow-xs"
                  : "bg-surface border border-line text-ink hover:bg-surface-alt"
              }`}
            >
              {token}
            </button>
          )
        )}

        <button
          type="button"
          onClick={() => go(current + 1)}
          disabled={disabled || current >= totalPages}
          className={arrowClass}
          aria-label="Go to next page"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            chevron_right
          </span>
        </button>
      </nav>
    </div>
  );
}
