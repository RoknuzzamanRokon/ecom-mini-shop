"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useSeller } from "@/components/seller/SellerGuard";
import {
  getSellerShops,
  getSellerProducts,
  getSellerOrders,
  getSellerWallet,
} from "@/lib/api";
import { SellerShop, Product, SellerOrder, SellerWallet } from "@/lib/types";

export default function SellerDashboardPage() {
  const { seller, capabilities, dashboardData } = useSeller();

  const [shops, setShops] = useState<SellerShop[]>([]);
  const [productsCount, setProductsCount] = useState<number>(0);
  const [orders, setOrders] = useState<SellerOrder[]>([]);
  const [ordersCount, setOrdersCount] = useState<number>(0);
  const [wallet, setWallet] = useState<SellerWallet | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(true);

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;

    if (!token) return;

    Promise.allSettled([
      getSellerShops(token).then((data) => setShops(data)),
      getSellerProducts(token, { page: 1 }).then((data) => setProductsCount(data.count)),
      getSellerOrders(token, undefined, 1).then((data) => {
        setOrders(data.results.slice(0, 5));
        setOrdersCount(data.count);
      }),
      getSellerWallet(token).then((data) => setWallet(data)),
    ]).finally(() => {
      setLoadingMetrics(false);
    });
  }, []);

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Welcome, {seller?.business_name || "Seller"}!
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Manage your stores, inventory, orders, and point balance from one centralized portal.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {seller?.is_operational ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-success/15 text-success border border-success/20">
              <span className="w-2 h-2 rounded-full bg-success"></span>
              Operational
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-accent/15 text-accent border border-accent/20">
              <span className="w-2 h-2 rounded-full bg-accent"></span>
              {seller?.status_display || "Not Operational"}
            </span>
          )}
          <span className="px-3 py-1 rounded-full text-xs font-bold bg-primary/10 text-primary border border-primary/20">
            {seller?.seller_type_display || seller?.seller_type}
          </span>
        </div>
      </div>

      {/* Account Alerts (Warning / Info) */}
      {dashboardData?.warning && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-medium flex items-center gap-3">
          <span className="material-symbols-outlined text-[22px] shrink-0">warning</span>
          <span>{dashboardData.warning}</span>
        </div>
      )}
      {dashboardData?.info && (
        <div className="p-4 rounded-xl bg-primary/10 border border-primary/30 text-primary text-xs font-medium flex items-center gap-3">
          <span className="material-symbols-outlined text-[22px] shrink-0">info</span>
          <span>{dashboardData.info}</span>
        </div>
      )}

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Shops Metric */}
        <div className="bg-surface rounded-xl border border-line p-5 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Registered Shops
            </p>
            <p className="text-2xl font-black text-ink mt-1">
              {loadingMetrics ? "..." : shops.length}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">
              {capabilities?.can_create_shops
                ? capabilities.max_shops
                  ? `Max limit: ${capabilities.max_shops}`
                  : "Unlimited shops allowed"
                : "Shop creation disabled"}
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[26px]">storefront</span>
          </div>
        </div>

        {/* Products Metric */}
        <div className="bg-surface rounded-xl border border-line p-5 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Listed Products
            </p>
            <p className="text-2xl font-black text-ink mt-1">
              {loadingMetrics ? "..." : productsCount}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">
              Active across your shops
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-accent/10 text-accent flex items-center justify-center">
            <span className="material-symbols-outlined text-[26px]">inventory_2</span>
          </div>
        </div>

        {/* Orders Metric */}
        <div className="bg-surface rounded-xl border border-line p-5 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Total Orders
            </p>
            <p className="text-2xl font-black text-ink mt-1">
              {loadingMetrics ? "..." : ordersCount}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">
              Orders with your items
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-success/10 text-success flex items-center justify-center">
            <span className="material-symbols-outlined text-[26px]">receipt_long</span>
          </div>
        </div>

        {/* Wallet Points Metric */}
        <div className="bg-surface rounded-xl border border-line p-5 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Points Balance
            </p>
            <p className="text-2xl font-black text-ink mt-1">
              {loadingMetrics ? "..." : `${wallet?.balance ?? 0}`}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">
              Points available for products
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[26px]">account_balance_wallet</span>
          </div>
        </div>
      </div>

      {/* Quick Action Shortcuts */}
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-ink mb-3">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link
            href="/seller/products"
            className="p-4 rounded-xl bg-surface border border-line hover:border-primary/40 hover:bg-surface-alt/50 transition-all flex items-center gap-3 group"
          >
            <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[22px]">add_box</span>
            </div>
            <div>
              <p className="text-xs font-bold text-ink">Manage Products</p>
              <p className="text-[11px] text-ink-muted">Add or edit catalog items</p>
            </div>
          </Link>

          <Link
            href="/seller/shops"
            className="p-4 rounded-xl bg-surface border border-line hover:border-primary/40 hover:bg-surface-alt/50 transition-all flex items-center gap-3 group"
          >
            <div className="w-10 h-10 rounded-lg bg-accent/10 text-accent flex items-center justify-center group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[22px]">store</span>
            </div>
            <div>
              <p className="text-xs font-bold text-ink">Manage Shops</p>
              <p className="text-[11px] text-ink-muted">Update shop information</p>
            </div>
          </Link>

          <Link
            href="/seller/orders"
            className="p-4 rounded-xl bg-surface border border-line hover:border-primary/40 hover:bg-surface-alt/50 transition-all flex items-center gap-3 group"
          >
            <div className="w-10 h-10 rounded-lg bg-success/10 text-success flex items-center justify-center group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[22px]">local_shipping</span>
            </div>
            <div>
              <p className="text-xs font-bold text-ink">Fulfill Orders</p>
              <p className="text-[11px] text-ink-muted">Process and ship customer items</p>
            </div>
          </Link>

          <Link
            href="/seller/wallet"
            className="p-4 rounded-xl bg-surface border border-line hover:border-primary/40 hover:bg-surface-alt/50 transition-all flex items-center gap-3 group"
          >
            <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[22px]">history</span>
            </div>
            <div>
              <p className="text-xs font-bold text-ink">Wallet &amp; Points</p>
              <p className="text-[11px] text-ink-muted">Inspect balance and history</p>
            </div>
          </Link>
        </div>
      </div>

      {/* Recent Orders Overview */}
      <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs">
        <div className="flex items-center justify-between pb-4 mb-4 border-b border-line">
          <div>
            <h2 className="text-base font-bold text-ink">Recent Orders</h2>
            <p className="text-xs text-ink-muted">Customer orders requiring your fulfillment</p>
          </div>
          <Link
            href="/seller/orders"
            className="text-xs font-bold uppercase tracking-wider text-primary hover:underline flex items-center gap-1"
          >
            <span>View All</span>
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>

        {loadingMetrics ? (
          <div className="py-8 text-center text-xs text-ink-muted">Loading orders...</div>
        ) : orders.length === 0 ? (
          <div className="py-8 text-center text-xs text-ink-muted">
            <span className="material-symbols-outlined text-[40px] opacity-40 mb-2 block">
              inbox
            </span>
            No customer orders received yet.
          </div>
        ) : (
          <div className="divide-y divide-line-subtle">
            {orders.map((ord) => (
              <div
                key={ord.id}
                className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-xs text-ink">
                      {ord.order_number}
                    </span>
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-primary/10 text-primary">
                      {ord.status}
                    </span>
                  </div>
                  <p className="text-xs text-ink-muted mt-1">
                    {ord.seller_item_count} item(s) · Subtotal: ৳{ord.seller_subtotal}
                    {ord.shipping_city ? ` · Ships to ${ord.shipping_city}` : ""}
                  </p>
                </div>
                <Link
                  href={`/seller/orders`}
                  className="text-xs font-semibold text-primary hover:underline inline-flex items-center gap-1"
                >
                  <span>Manage</span>
                  <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
