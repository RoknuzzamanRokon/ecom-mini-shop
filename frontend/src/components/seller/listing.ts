/**
 * Listing periods on the seller side (docs/LISTING_VALIDITY_PLAN.md): a
 * Limited Shop Owner's product is live until `live_until`, then EXPIRED until
 * the seller renews it. A Full Shop Owner's products have no end date.
 */

import { formatDate } from "@/lib/admin-format";
import type { Product, UpcomingPointExpiry } from "@/lib/types";

const DAY_MS = 24 * 60 * 60 * 1000;

/** Whole days until `iso`, rounded up; 0 once it has passed. */
export function daysLeft(iso: string, now: number = Date.now()): number {
  const ms = new Date(iso).getTime() - now;
  return ms > 0 ? Math.ceil(ms / DAY_MS) : 0;
}

/** One line on a product's listing period, or null when there is nothing to say. */
export function listingPeriodLine(product: Pick<Product, "status" | "live_until">): string | null {
  if (product.status === "EXPIRED" && product.live_until) {
    return `Expired ${formatDate(product.live_until)}`;
  }
  if (product.status !== "PUBLISHED") return null;
  return product.live_until ? `Live until ${formatDate(product.live_until)}` : "No end date";
}

/**
 * The wallet's upcoming expiries merged by date. Each purchase gives all of
 * a seller's unspent points one date, so several batches usually share it.
 */
export function expiriesByDate(lots: UpcomingPointExpiry[]): UpcomingPointExpiry[] {
  const merged = new Map<string, number>();
  for (const lot of lots) {
    merged.set(lot.expires_at, (merged.get(lot.expires_at) ?? 0) + lot.points);
  }
  return Array.from(merged, ([expires_at, points]) => ({ expires_at, points }));
}
