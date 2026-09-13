const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export interface AdminMetrics {
  total_orders: number;
  total_revenue: number;
  pending_shops: number;
  pending_sellers: number;
  total_shops: number;
  total_sellers: number;
  total_products: number;
}

/**
 * Fetches platform-wide operational metrics for the Next.js Management Console.
 * Returns real backend aggregates for orders, revenue (in ৳), pending shops, and pending sellers.
 */
export async function getAdminMetrics(token: string): Promise<AdminMetrics> {
  const res = await fetch(`${API_BASE_URL}/api/admin/metrics/`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || "Failed to load management metrics.");
  }

  return await res.json();
}
