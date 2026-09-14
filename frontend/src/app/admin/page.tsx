"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { getAdminMetrics, AdminMetrics, AdminApiError } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS, getAccessibleNavItems } from "@/lib/admin-navigation";
import { AdminStatCard } from "@/components/admin/shared";

/** Small "needs attention" pill used beside backlog counts. */
function NeedsActionBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="text-[10px] uppercase font-extrabold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600">
      Needs Action
    </span>
  );
}

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    const token = getAuthToken();

    if (!token) {
      setLoading(false);
      setError("No active session token was found. Please sign in again.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminMetrics(token);
      setMetrics(data);
    } catch (err: unknown) {
      const message =
        err instanceof AdminApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to load management metrics.";
      console.warn("Failed to fetch admin metrics:", err);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  /**
   * ==========================================================================
   * PERMISSION-DRIVEN KPI VISIBILITY
   * ==========================================================================
   * There is one dashboard for all seven management roles, not seven dashboards.
   * What each operator sees is derived from their permissions, never from a
   * hardcoded role branch. Access to /admin alone reveals no financial data:
   * revenue requires payments.view or reports.view.
   *
   * The metrics endpoint returns the full aggregate payload to any management
   * user, so this gating is a UI-surface decision. Restricting the payload
   * per-permission would be a backend change, which is out of scope here.
   */
  const showRevenue = hasAnyPermission(user, ADMIN_PERMISSIONS.metricRevenue);
  const showOrders = hasAnyPermission(user, ADMIN_PERMISSIONS.metricOrders);
  const showShops = hasAnyPermission(user, ADMIN_PERMISSIONS.metricShops);
  const showSellers = hasAnyPermission(user, ADMIN_PERMISSIONS.metricSellers);
  const showProducts = hasAnyPermission(user, ADMIN_PERMISSIONS.metricProducts);

  const showCatalogPanel = showShops || showSellers || showProducts;
  const visibleKpiCount = [
    showOrders,
    showRevenue,
    showShops,
    showSellers,
  ].filter(Boolean).length;

  /**
   * Quick actions reuse the same permission-filtered navigation model as the
   * sidebar, so a shortcut can never point at a module the operator cannot open.
   */
  const quickActions = React.useMemo(
    () => getAccessibleNavItems(user).filter((item) => item.href !== "/admin"),
    [user]
  );

  return (
    <div className="space-y-6">
      {/* Page Title & Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Platform Overview
          </h1>
          <p className="text-xs text-ink-muted">
            High-level operational metrics and system monitoring for MiniShop administrators.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchMetrics}
          disabled={loading}
          className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span
            aria-hidden="true"
            className={`material-symbols-outlined text-[16px] ${loading ? "animate-spin" : ""}`}
          >
            refresh
          </span>
          <span>Refresh Data</span>
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 text-xs flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0">
              warning
            </span>
            <span className="truncate">{error}</span>
          </div>
          <button
            type="button"
            onClick={fetchMetrics}
            className="underline font-bold hover:text-red-700 shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Permission-gated KPI grid */}
      {visibleKpiCount > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {showOrders && (
            <AdminStatCard
              title="Total Orders"
              value={metrics?.total_orders}
              icon="receipt_long"
              tone="info"
              loading={loading}
              description="Platform-wide customer orders"
            />
          )}

          {showRevenue && (
            <AdminStatCard
              title="Total Revenue"
              value={metrics?.total_revenue}
              currency
              icon="payments"
              tone="success"
              loading={loading}
              description="Cleared transactions"
            />
          )}

          {showShops && (
            <AdminStatCard
              title="Pending Shops"
              value={metrics?.pending_shops}
              icon="storefront"
              tone="warning"
              loading={loading}
              description="Awaiting staff review"
              badge={<NeedsActionBadge count={metrics?.pending_shops ?? 0} />}
            />
          )}

          {showSellers && (
            <AdminStatCard
              title="Pending Sellers"
              value={metrics?.pending_sellers}
              icon="badge"
              tone="accent"
              loading={loading}
              description="KYC applications pending"
              badge={<NeedsActionBadge count={metrics?.pending_sellers ?? 0} />}
            />
          )}
        </div>
      )}

      {/* Operator holds no metric permission at all */}
      {visibleKpiCount === 0 && !showCatalogPanel && (
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 text-center">
          <div className="w-12 h-12 mx-auto rounded-2xl bg-surface-alt text-ink-muted flex items-center justify-center mb-3">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              query_stats
            </span>
          </div>
          <p className="text-sm font-bold text-ink">No metrics available</p>
          <p className="text-xs text-ink-muted mt-1 max-w-md mx-auto">
            Your account does not hold any of the permissions required to view platform
            metrics. Use the navigation to reach the modules assigned to you.
          </p>
        </div>
      )}

      {/* Secondary stats & permission-driven shortcuts */}
      {(showCatalogPanel || quickActions.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {showCatalogPanel && (
            <div className="bg-surface p-6 rounded-2xl border border-line shadow-xs space-y-4">
              <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
                Catalog Inventory
              </h2>
              <dl className="space-y-3">
                {showShops && (
                  <div className="flex items-center justify-between py-2 border-b border-line text-xs">
                    <dt className="text-ink-muted flex items-center gap-2">
                      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                        store
                      </span>
                      Active Shops
                    </dt>
                    <dd className="font-bold text-ink">{metrics?.total_shops ?? "—"}</dd>
                  </div>
                )}
                {showSellers && (
                  <div className="flex items-center justify-between py-2 border-b border-line text-xs">
                    <dt className="text-ink-muted flex items-center gap-2">
                      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                        groups
                      </span>
                      Registered Sellers
                    </dt>
                    <dd className="font-bold text-ink">{metrics?.total_sellers ?? "—"}</dd>
                  </div>
                )}
                {showProducts && (
                  <div className="flex items-center justify-between py-2 text-xs">
                    <dt className="text-ink-muted flex items-center gap-2">
                      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                        inventory_2
                      </span>
                      Listed Products
                    </dt>
                    <dd className="font-bold text-ink">{metrics?.total_products ?? "—"}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}

          {quickActions.length > 0 && (
            <div
              className={`bg-surface p-6 rounded-2xl border border-line shadow-xs space-y-4 ${
                showCatalogPanel ? "lg:col-span-2" : "lg:col-span-3"
              }`}
            >
              <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
                Operational Shortcuts
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {quickActions.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="p-3.5 rounded-xl bg-surface-alt hover:bg-surface-sunken border border-line transition-all flex items-center justify-between gap-3 group focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 shrink-0 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                        <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
                          {item.icon}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-ink truncate">{item.label}</p>
                        <p className="text-[10px] text-ink-muted line-clamp-1">
                          {item.description}
                        </p>
                      </div>
                    </div>
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[18px] text-ink-muted group-hover:text-primary transition-colors shrink-0"
                    >
                      arrow_forward
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
