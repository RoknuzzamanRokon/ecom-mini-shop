"use client";

import React from "react";

interface PaginationProps {
  currentPage?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
}

export default function Pagination({
  currentPage = 1,
  totalPages = 3,
  onPageChange,
}: PaginationProps) {
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <div className="flex items-center justify-center gap-2 mt-4 pt-4 border-t border-line">
      <button
        onClick={() => onPageChange && onPageChange(Math.max(currentPage - 1, 1))}
        disabled={currentPage <= 1}
        className="w-9 h-9 rounded bg-surface border border-line text-ink-muted shadow-xs hover:bg-surface-alt flex items-center justify-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        title="Previous page"
        type="button"
      >
        <span className="material-symbols-outlined text-[18px]">chevron_left</span>
      </button>

      {pages.map((page) => (
        <button
          key={page}
          onClick={() => onPageChange && onPageChange(page)}
          className={`w-9 h-9 rounded text-xs font-semibold flex items-center justify-center shadow-xs transition-colors cursor-pointer ${
            currentPage === page
              ? "bg-primary text-on-primary shadow-xs"
              : "bg-surface border border-line text-ink hover:bg-surface-alt"
          }`}
          type="button"
        >
          {page}
        </button>
      ))}

      <button
        onClick={() => onPageChange && onPageChange(Math.min(currentPage + 1, totalPages))}
        disabled={currentPage >= totalPages}
        className="w-9 h-9 rounded bg-surface border border-line text-ink-muted shadow-xs hover:bg-surface-alt flex items-center justify-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        title="Next page"
        type="button"
      >
        <span className="material-symbols-outlined text-[18px]">chevron_right</span>
      </button>
    </div>
  );
}
