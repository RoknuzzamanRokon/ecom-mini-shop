"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Pagination from "@/components/home/Pagination";
import OrderCard, { ACTIVE_STATUSES } from "@/components/profile/OrderCard";
import { Order } from "@/lib/types";
import { getUserOrders } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

const PAGE_SIZE = 10;

export default function CurrentOrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getAuthToken();
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      // Filtered by the server, so an older active order is never hidden
      // behind a page of newer finished ones (BUG-026).
      const res = await getUserOrders(token, page, { pageSize: PAGE_SIZE, statuses: ACTIVE_STATUSES });
      setOrders(res.results);
      setTotalPages(Math.max(1, Math.ceil(res.count / PAGE_SIZE)));
    } catch {
      setError("We could not load your current orders. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-ink">Current Orders</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            Orders on the way to you, with live delivery status.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-primary hover:bg-surface-alt px-3 py-2 rounded-lg transition-colors disabled:opacity-60 cursor-pointer"
        >
          <span className="material-symbols-outlined text-[16px]">refresh</span>
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            local_shipping
          </span>
          <p className="text-sm text-ink-body mt-2">Checking your deliveries…</p>
        </div>
      ) : error ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center">
          <p className="text-sm text-accent font-medium">{error}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[56px] text-ink-muted/40">
            local_shipping
          </span>
          <h2 className="text-base font-bold text-ink mt-2">No active orders</h2>
          <p className="text-sm text-ink-body mt-1 mb-5">
            Nothing is on the way right now. Past orders live in your order history.
          </p>
          <Link
            href="/profile/orders"
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
          >
            View Order History
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              showTracker
              onOrderUpdated={(updated) =>
                setOrders((prev) =>
                  prev.filter((o) =>
                    o.id === updated.id
                      ? ACTIVE_STATUSES.includes((updated.status || "").toUpperCase())
                      : true
                  )
                )
              }
            />
          ))}
          {totalPages > 1 && (
            <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
          )}
        </div>
      )}
    </div>
  );
}
