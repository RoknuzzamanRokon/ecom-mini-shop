/**
 * Shared formatting helpers for the MiniShop Management Console.
 *
 * All formatters are locale-pinned (never the runtime's implicit locale) so that
 * server-rendered and client-rendered output are byte-identical and cannot
 * trigger React hydration mismatches.
 *
 * Currency is always Bangladeshi Taka (৳) per the MiniShop currency rule.
 */

export const CURRENCY_SYMBOL = "৳";

/** Backend decimal fields arrive as strings; coerce defensively to a finite number. */
export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Formats a monetary amount as ৳ with thousands separators.
 * Never emits "$", "USD", or "BDT".
 */
export function formatTaka(
  value: string | number | null | undefined,
  options: { decimals?: number } = {}
): string {
  const { decimals = 2 } = options;
  const amount = toNumber(value);
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
  return `${CURRENCY_SYMBOL}${formatted}`;
}

/** Compact ৳ rendering for dense stat tiles (৳12.4K, ৳3.1M). */
export function formatTakaCompact(value: string | number | null | undefined): string {
  const amount = toNumber(value);
  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `${CURRENCY_SYMBOL}${(amount / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${CURRENCY_SYMBOL}${(amount / 1_000).toFixed(1)}K`;
  return formatTaka(amount);
}

/** Integer counts with thousands separators. */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "0";
  return new Intl.NumberFormat("en-US").format(value);
}

/** Human-readable date, e.g. "14 Sep 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

/** Human-readable date and time, e.g. "14 Sep 2026, 19:58". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * Converts a backend enum token into a display label.
 * "UNDER_REVIEW" -> "Under Review", "partially_refunded" -> "Partially Refunded".
 */
export function humanizeToken(token: string): string {
  return token
    .replace(/[_-]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}
