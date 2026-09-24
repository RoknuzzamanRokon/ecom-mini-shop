"use client";

import React from "react";
import Image from "next/image";
import Link from "next/link";
import StarRating from "@/components/reviews/StarRating";
import { formatImageUrl } from "@/lib/api";
import { formatDistance } from "@/lib/geolocation";
import { NearbyShop } from "@/lib/types";

interface NearbyShopCardProps {
  shop: NearbyShop;
  /** 1-based rank by distance; the same number is shown on the shop's map marker. */
  rank: number;
  selected: boolean;
  onSelect: (shopId: number) => void;
  /** When given, a "Show on map" button selects the shop and brings the map to it. */
  onShowOnMap?: (shopId: number) => void;
}

/**
 * One nearby-shop result. Clicking the card selects the shop (mouse
 * convenience); the keyboard path is the "Show on map" button, and "View Shop"
 * is a client-side link so the customer's in-memory location survives it.
 */
export default function NearbyShopCard({
  shop,
  rank,
  selected,
  onSelect,
  onShowOnMap,
}: NearbyShopCardProps) {
  const rated = (shop.review_count ?? 0) > 0;

  return (
    <article
      id={`nearby-shop-${shop.id}`}
      onClick={() => onSelect(shop.id)}
      className={`relative flex gap-3 rounded-xl border bg-surface p-3 transition-shadow cursor-pointer scroll-mt-36 ${
        selected
          ? "border-primary ring-2 ring-primary/25 shadow-md"
          : "border-line shadow-xs hover:shadow-md"
      }`}
    >
      <div className="relative shrink-0">
        <div className="w-14 h-14 rounded-lg border border-line bg-surface-alt overflow-hidden flex items-center justify-center">
          {shop.logo ? (
            <Image
              src={formatImageUrl(shop.logo)}
              alt=""
              width={56}
              height={56}
              className="object-cover w-full h-full"
            />
          ) : (
            <span aria-hidden="true" className="material-symbols-outlined text-[26px] text-primary">
              storefront
            </span>
          )}
        </div>
        <span
          aria-hidden="true"
          className={`absolute -top-1.5 -left-1.5 min-w-5 h-5 px-1 rounded-full border-2 border-surface text-[10px] font-bold flex items-center justify-center ${
            selected ? "bg-accent text-on-accent" : "bg-primary text-on-primary"
          }`}
        >
          {rank}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-bold text-ink leading-snug truncate">
            <span className="sr-only">{rank}. </span>
            {shop.name}
          </h3>
          <span className="shrink-0 inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-bold text-primary">
            <span aria-hidden="true" className="material-symbols-outlined text-[13px]">
              near_me
            </span>
            {formatDistance(shop.distance_km)}
            <span className="sr-only"> away</span>
          </span>
        </div>

        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-muted">
          <StarRating rating={shop.average_rating ?? 0} size={12} />
          {rated ? (
            <span>
              <strong className="text-ink">{(shop.average_rating ?? 0).toFixed(1)}</strong> (
              {shop.review_count})
            </span>
          ) : (
            <span>No reviews yet</span>
          )}
        </div>

        {shop.address && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-ink-muted">
            <span aria-hidden="true" className="material-symbols-outlined text-[13px] shrink-0">
              location_on
            </span>
            <span className="truncate">{shop.address}</span>
          </p>
        )}

        <div className="mt-2 flex items-center gap-4">
          {onShowOnMap && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onShowOnMap(shop.id);
              }}
              aria-pressed={selected}
              className="inline-flex items-center gap-1 py-1 text-[11px] font-bold text-ink-muted hover:text-primary transition-colors cursor-pointer rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                pin_drop
              </span>
              Show on map
              <span className="sr-only">: {shop.name}</span>
            </button>
          )}
          <Link
            href={`/shop/${shop.slug}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-0.5 py-1 text-[11px] font-bold text-primary hover:underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            View Shop
            <span className="sr-only">: {shop.name}</span>
            <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
              arrow_forward
            </span>
          </Link>
        </div>
      </div>
    </article>
  );
}

/** Placeholder with the card's shape, for the loading state. */
export function NearbyShopCardSkeleton() {
  return (
    <div aria-hidden="true" className="flex gap-3 rounded-xl border border-line bg-surface p-3">
      <div className="w-14 h-14 rounded-lg bg-surface-alt animate-pulse shrink-0" />
      <div className="flex-1 space-y-2 py-0.5">
        <div className="flex justify-between gap-2">
          <div className="h-4 w-2/5 rounded bg-surface-alt animate-pulse" />
          <div className="h-4 w-12 rounded-full bg-surface-alt animate-pulse" />
        </div>
        <div className="h-3 w-1/3 rounded bg-surface-alt animate-pulse" />
        <div className="h-3 w-3/5 rounded bg-surface-alt animate-pulse" />
      </div>
    </div>
  );
}
