"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Pagination from "@/components/home/Pagination";
import OrderCard from "@/components/profile/OrderCard";
import { Order } from "@/lib/types";
import { getUserOrders } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

const PAGE_SIZE = 10;

export default function OrderHistoryPage() {
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
      const res = await getUserOrders(token, page);
      setOrders(res.results);
      setTotalPages(Math.max(Math.ceil(res.count / PAGE_SIZE), 1));
    } catch {
      setError("We could not load your orders. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-bold text-ink">Order History</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Every order you have placed, newest first.
        </p>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            receipt_long
          </span>
          <p className="text-sm text-ink-body mt-2">Loading orders…</p>
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
            receipt_long
          </span>
          <h2 className="text-base font-bold text-ink mt-2">No orders yet</h2>
          <p className="text-sm text-ink-body mt-1 mb-5">
            When you place an order it will appear here.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
          >
            Start Shopping
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-4">
            {orders.map((order) => (
              <OrderCard key={order.id} order={order} />
            ))}
          </div>
          {totalPages > 1 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          )}
        </>
      )}
    </div>
  );
}
