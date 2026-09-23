"use client";

import React, { useState } from "react";

interface StarPickerProps {
  value: number;
  onChange: (rating: number) => void;
}

/** Clickable 1–5 star input with hover preview. */
export default function StarPicker({ value, onChange }: StarPickerProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const active = hovered ?? value;

  return (
    <div className="flex items-center gap-0.5 text-star">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          onMouseEnter={() => setHovered(n)}
          onMouseLeave={() => setHovered(null)}
          className="cursor-pointer"
          aria-label={`${n} star${n === 1 ? "" : "s"}`}
          aria-pressed={n === value}
        >
          <span
            className={`material-symbols-outlined text-[22px] ${n <= active ? "fill-active" : ""}`}
          >
            star
          </span>
        </button>
      ))}
    </div>
  );
}
