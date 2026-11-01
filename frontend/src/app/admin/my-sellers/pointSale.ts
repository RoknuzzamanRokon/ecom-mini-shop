import type { AdminOnboardingSeller, AdminPointSaleResult } from "@/lib/admin-api";
import { formatCount, formatDate } from "@/lib/admin-format";

/** OnboardingService.sell_points sells only to sellers staff approved. */
export function canBuyPoints(seller: Pick<AdminOnboardingSeller, "status">): boolean {
  return seller.status === "APPROVED" || seller.status === "ACTIVE";
}

/** Why `text` cannot be sold, or null when it can. */
export function saleAmountError(text: string, minimum: number, available: number): string | null {
  if (!/^\d+$/.test(text.trim())) return "Enter a whole number of points.";
  const amount = Number(text);
  if (amount < minimum) return `The minimum sale is ${formatCount(minimum)} points.`;
  if (amount > available) return `Your wallet holds ${formatCount(available)} points.`;
  return null;
}

/** One-click amounts: the minimum and a few round sizes the wallet can cover. */
export function quickAmounts(minimum: number, available: number): number[] {
  return Array.from(new Set([minimum, 200, 500, 1000]))
    .filter((amount) => amount >= minimum && amount <= available)
    .sort((a, b) => a - b);
}

/** What the page says after a sale. A Full Shop Owner's points never expire, so no date for them. */
export function saleSummary(seller: Pick<AdminOnboardingSeller, "business_name" | "seller_type">, result: AdminPointSaleResult): string {
  const validity =
    seller.seller_type === "LIMITED_SHOP_OWNER" ? `, valid until ${formatDate(result.points_expire_at)}` : "";
  return (
    `Sold ${formatCount(result.amount)} points to ${seller.business_name}. ` +
    `They now hold ${formatCount(result.points_balance)} points${validity}. ` +
    `Your wallet holds ${formatCount(result.your_points)}.`
  );
}
