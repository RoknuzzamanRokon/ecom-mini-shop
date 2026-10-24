"use client";

import React from "react";
import Image from "next/image";
import { formatImageUrl } from "@/lib/api";

/**
 * The gallery thumbnails under a product's main image. Each button says which
 * picture it shows, and the one on screen is marked pressed (BUG-094); the
 * thumbnail image itself is decorative.
 */
export default function ProductThumbnails({
  images,
  selected,
  onSelect,
}: {
  /** Raw image URLs, as the API sends them. */
  images: string[];
  /** The formatted URL of the image on screen. */
  selected: string;
  onSelect: (formattedUrl: string) => void;
}) {
  if (images.length < 2) return null;

  return (
    <div role="group" aria-label="Product images" className="flex gap-2.5 overflow-x-auto pb-1">
      {images.map((img, i) => {
        const formattedThumb = formatImageUrl(img);
        const isSelected = selected === formattedThumb;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(formattedThumb)}
            aria-label={`Show image ${i + 1} of ${images.length}`}
            aria-pressed={isSelected}
            className={`relative w-16 h-16 rounded-md overflow-hidden border-2 shrink-0 transition-all cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
              isSelected ? "border-primary shadow-xs" : "border-line hover:border-ink-muted"
            }`}
          >
            <Image src={formattedThumb} alt="" fill sizes="64px" className="object-cover" />
          </button>
        );
      })}
    </div>
  );
}
