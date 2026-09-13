"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getAdminMetrics, AdminMetrics } from "@/lib/admin-api";
import { hasManagementPermission } from "@/lib/admin-auth";

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token")
        : null;

    if (!token) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminMetrics(token);
      setMetrics(data);
    } catch (err: any) {
      console.warn("Failed to fetch admin metrics:", err);
      setError(err?.message || "Failed to load management metrics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  const canManageShops = hasManagementPermission(user, [
    "shops.admin.manage",
    "shops.view",
    "shop:read",
  ]);
  const canManageSellers = hasManagementPermission(user, [
    "sellers.admin.manage",
    "sellers.view",
    "seller:read",
  ]);
  const canManageOrders = hasManagementPermission(user, [
    "orders.staff.view",
    "orders.view",
    "order:read",
  ]);
  const canManagePayments = hasManagementPermission(user, [
    "payments.view",
    "payments.verify",
    "payment:read",
  ]);

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
          className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-50"
        >
          <span
            className={`material-symbols-outlined text-[16px] ${
              loading ? "animate-spin" : ""
            }`}
          >
            refresh
          </span>
          <span>Refresh Data</span>
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">warning</span>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={fetchMetrics}
            className="underline font-bold hover:text-red-700"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Total Platform Orders */}
        <div className="bg-surface p-5 rounded-2xl border border-line shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Total Orders
            </span>
            <div className="w-9 h-9 rounded-xl bg-blue-500/10 text-blue-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">
                receipt_long
              </span>
            </div>
          </div>
          <div className="mt-4">
            {loading ? (
              <div className="h-8 w-20 bg-surface-alt animate-pulse rounded-md" />
            ) : (
              <div className="text-2xl font-black text-ink">
                {metrics?.total_orders?.toLocaleString() ?? "0"}
              </div>
            )}
            <p className="text-[11px] text-ink-muted mt-1">Platform-wide customer orders</p>
          </div>
        </div>

        {/* Metric 2: Total Platform Revenue */}
        <div className="bg-surface p-5 rounded-2xl border border-line shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Total Revenue
            </span>
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">payments</span>
            </div>
          </div>
          <div className="mt-4">
            {loading ? (
              <div className="h-8 w-28 bg-surface-alt animate-pulse rounded-md" />
            ) : (
              <div className="text-2xl font-black text-ink">
                ৳{metrics?.total_revenue?.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                }) ?? "0.00"}
              </div>
            )}
            <p className="text-[11px] text-ink-muted mt-1">Cleared transactions</p>
          </div>
        </div>

        {/* Metric 3: Pending Shop Approvals */}
        <div className="bg-surface p-5 rounded-2xl border border-line shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Pending Shops
            </span>
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 text-amber-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">storefront</span>
            </div>
          </div>
          <div className="mt-4">
            {loading ? (
              <div className="h-8 w-16 bg-surface-alt animate-pulse rounded-md" />
            ) : (
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-ink">
                  {metrics?.pending_shops ?? 0}
                </span>
                {(metrics?.pending_shops ?? 0) > 0 && (
                  <span className="text-[10px] uppercase font-extrabold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-700">
                    Needs Action
                  </span>
                )}
              </div>
            )}
            <p className="text-[11px] text-ink-muted mt-1">Awaiting staff review</p>
          </div>
        </div>

        {/* Metric 4: Pending Seller Verifications */}
        <div className="bg-surface p-5 rounded-2xl border border-line shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Pending Sellers
            </span>
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">badge</span>
            </div>
          </div>
          <div className="mt-4">
            {loading ? (
              <div className="h-8 w-16 bg-surface-alt animate-pulse rounded-md" />
            ) : (
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-ink">
                  {metrics?.pending_sellers ?? 0}
                </span>
                {(metrics?.pending_sellers ?? 0) > 0 && (
                  <span className="text-[10px] uppercase font-extrabold px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-700">
                    Needs Action
                  </span>
                )}
              </div>
            )}
            <p className="text-[11px] text-ink-muted mt-1">KYC applications pending</p>
          </div>
        </div>
      </div>

      {/* Secondary Operational Stats & Quick Modules */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* System Catalog Statistics */}
        <div className="bg-surface p-6 rounded-2xl border border-line shadow-xs space-y-4">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
            Catalog Inventory
          </h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-line text-xs">
              <span className="text-ink-muted flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">store</span>
                Active Shops
              </span>
              <span className="font-bold text-ink">
                {metrics?.total_shops ?? "—"}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-line text-xs">
              <span className="text-ink-muted flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">groups</span>
                Registered Sellers
              </span>
              <span className="font-bold text-ink">
                {metrics?.total_sellers ?? "—"}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 text-xs">
              <span className="text-ink-muted flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">inventory_2</span>
                Listed Products
              </span>
              <span className="font-bold text-ink">
                {metrics?.total_products ?? "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Quick Operations Module Navigation */}
        <div className="lg:col-span-2 bg-surface p-6 rounded-2xl border border-line shadow-xs space-y-4">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
            Operational Shortcuts
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {canManageShops && (
              <Link
                href="/admin/shops"
                className="p-3.5 rounded-xl bg-surface-alt hover:bg-surface-sunken border border-line transition-all flex items-center justify-between group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[20px]">storefront</span>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-ink">Shop Governance</p>
                    <p className="text-[10px] text-ink-muted">Approve and inspect shops</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-[18px] text-ink-muted group-hover:text-primary transition-colors">
                  arrow_forward
                </span>
              </Link>
            )}

            {canManageSellers && (
              <Link
                href="/admin/sellers"
                className="p-3.5 rounded-xl bg-surface-alt hover:bg-surface-sunken border border-line transition-all flex items-center justify-between group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[20px]">badge</span>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-ink">Seller KYC Verification</p>
                    <p className="text-[10px] text-ink-muted">Verify merchant accounts</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-[18px] text-ink-muted group-hover:text-primary transition-colors">
                  arrow_forward
                </span>
              </Link>
            )}

            {canManageOrders && (
              <Link
                href="/admin/orders"
                className="p-3.5 rounded-xl bg-surface-alt hover:bg-surface-sunken border border-line transition-all flex items-center justify-between group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[20px]">receipt_long</span>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-ink">Staff Order Operations</p>
                    <p className="text-[10px] text-ink-muted">Fulfillment & status updates</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-[18px] text-ink-muted group-hover:text-primary transition-colors">
                  arrow_forward
                </span>
              </Link>
            )}

            {canManagePayments && (
              <Link
                href="/admin/payments"
                className="p-3.5 rounded-xl bg-surface-alt hover:bg-surface-sunken border border-line transition-all flex items-center justify-between group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[20px]">payments</span>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-ink">Financial Clearance</p>
                    <p className="text-[10px] text-ink-muted">Verify & refund payments</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-[18px] text-ink-muted group-hover:text-primary transition-colors">
                  arrow_forward
                </span>
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
