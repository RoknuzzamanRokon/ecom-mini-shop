/**
 * Listing periods on the seller side (docs/LISTING_VALIDITY_PLAN.md): a
 * Limited Shop Owner's product is live until `live_until`, then EXPIRED until
 * the seller renews or deletes it. A live one can be renewed early
 * (docs/FOLLOW_UPS_PLAN.md). A Full Shop Owner's products have no end date.
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

/** Whether the seller can renew the product: live with an end date, or expired. */
export function canRenew(product: Pick<Product, "status" | "listing_locked">): boolean {
  return product.status === "EXPIRED" || (product.status === "PUBLISHED" && Boolean(product.listing_locked));
}

/** Whether the seller can delete the product: only once it has expired. */
export function canDelete(product: Pick<Product, "status">): boolean {
  return product.status === "EXPIRED";
}

/** `date` moved `months` calendar months on, clamping the day like points.models.add_months. */
export function addMonths(date: Date, months: number): Date {
  const monthIndex = date.getUTCMonth() + months;
  const year = date.getUTCFullYear() + Math.floor(monthIndex / 12);
  const month = ((monthIndex % 12) + 12) % 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const moved = new Date(date.getTime());
  moved.setUTCFullYear(year, month, Math.min(date.getUTCDate(), lastDay));
  return moved;
}

/**
 * The end date a renewal would give: the months go on after the current end
 * date while the product is live, and start now once it has expired.
 */
export function renewedUntil(
  product: Pick<Product, "status" | "listing_locked" | "live_until">,
  months: number,
  now: number = Date.now()
): string {
  const start = product.status === "PUBLISHED" && product.listing_locked && product.live_until
    ? new Date(product.live_until)
    : new Date(now);
  return addMonths(start, months).toISOString();
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
