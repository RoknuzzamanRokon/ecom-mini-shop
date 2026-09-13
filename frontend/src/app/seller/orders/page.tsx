"use client";

import React, { useState, useEffect, useCallback } from "react";
import { getSellerOrders, updateSellerOrderStatus } from "@/lib/api";
import { SellerOrder } from "@/lib/types";

const ORDER_STATUSES = [
  "ALL",
  "PENDING",
  "CONFIRMED",
  "PROCESSING",
  "SHIPPED",
  "DELIVERED",
  "CANCELLED",
];

export default function SellerOrdersPage() {
  const [orders, setOrders] = useState<SellerOrder[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Order Details Modal / Drawer
  const [viewingOrder, setViewingOrder] = useState<SellerOrder | null>(null);

  // Status Update Modal
  const [updatingOrder, setUpdatingOrder] = useState<SellerOrder | null>(null);
  const [newStatus, setNewStatus] = useState<string>("");
  const [statusNote, setStatusNote] = useState<string>("");
  const [updatingLoading, setUpdatingLoading] = useState<boolean>(false);

  // Notifications
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchOrdersList = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    try {
      setLoading(true);
      const res = await getSellerOrders(
        token,
        selectedStatus !== "ALL" ? selectedStatus : undefined,
        page
      );
      // Filter locally or pass query if backend supports
      let filtered = res.results;
      if (selectedStatus !== "ALL") {
        filtered = filtered.filter(
          (o) => o.status.toUpperCase() === selectedStatus.toUpperCase()
        );
      }
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter(
          (o) =>
            o.order_number.toLowerCase().includes(q) ||
            o.shipping_recipient_name?.toLowerCase().includes(q) ||
            o.customer_name?.toLowerCase().includes(q)
        );
      }
      setOrders(filtered);
      setTotalCount(res.count);
      setTotalPages(Math.ceil(res.count / 10) || 1);
    } catch (err: any) {
      setActionError(err.message || "Failed to load seller orders.");
    } finally {
      setLoading(false);
    }
  }, [page, selectedStatus, searchQuery]);

  useEffect(() => {
    fetchOrdersList();
  }, [fetchOrdersList]);

  const handleOpenStatusModal = (order: SellerOrder) => {
    setUpdatingOrder(order);
    setNewStatus(order.status);
    setStatusNote("");
    setActionError(null);
  };

  const handleStatusSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!updatingOrder) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    setUpdatingLoading(true);
    setActionError(null);

    try {
      await updateSellerOrderStatus(
        updatingOrder.order_number,
        newStatus,
        token,
        statusNote || undefined
      );

      setActionSuccess(`Order ${updatingOrder.order_number} status updated to ${newStatus}.`);
      setUpdatingOrder(null);
      await fetchOrdersList();
    } catch (err: any) {
      setActionError(err.message || "Failed to update order status.");
    } finally {
      setUpdatingLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Seller Orders
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Track and fulfill customer orders containing items from your shops.
          </p>
        </div>
      </div>

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>{actionSuccess}</span>
        </div>
      )}

      {actionError && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{actionError}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-surface rounded-xl border border-line p-4 shadow-xs flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="w-full sm:w-72">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search order #, customer..."
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          {ORDER_STATUSES.map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setSelectedStatus(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap cursor-pointer ${
                selectedStatus === st
                  ? "bg-primary text-on-primary shadow-xs"
                  : "bg-surface-alt hover:bg-surface-sunken text-ink-body"
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Orders List */}
      <div className="space-y-4">
        {loading ? (
          <div className="py-12 text-center text-xs text-ink-muted">Loading orders...</div>
        ) : orders.length === 0 ? (
          <div className="bg-surface rounded-2xl border border-line p-12 text-center text-ink-muted text-xs">
            <span className="material-symbols-outlined text-[48px] opacity-40 mb-2 block">
              receipt_long
            </span>
            No orders found matching your filters.
          </div>
        ) : (
          orders.map((order) => {
            const isDelivered = order.status === "DELIVERED";
            const isCancelled = order.status === "CANCELLED";

            return (
              <div
                key={order.id}
                className="bg-surface rounded-2xl border border-line shadow-xs overflow-hidden"
              >
                {/* Order Header */}
                <div className="p-4 sm:p-5 bg-surface-alt/40 border-b border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono font-bold text-sm text-ink">
                        {order.order_number}
                      </span>
                      <span
                        className={`text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-md border ${
                          isDelivered
                            ? "bg-success/15 text-success border-success/20"
                            : isCancelled
                            ? "bg-accent/15 text-accent border-accent/20"
                            : "bg-primary/15 text-primary border-primary/20"
                        }`}
                      >
                        {order.status}
                      </span>
                    </div>
                    <p className="text-xs text-ink-muted mt-1">
                      Placed on {new Date(order.created_at).toLocaleDateString()}
                      {order.shipping_city ? ` · Destination: ${order.shipping_city}` : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setViewingOrder(order)}
                      className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-xs transition-colors cursor-pointer"
                    >
                      View Details
                    </button>
                    {!isCancelled && !isDelivered && (
                      <button
                        type="button"
                        onClick={() => handleOpenStatusModal(order)}
                        className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-semibold text-xs transition-colors shadow-xs cursor-pointer"
                      >
                        Update Status
                      </button>
                    )}
                  </div>
                </div>

                {/* Seller's Order Items */}
                <div className="p-4 sm:p-5 divide-y divide-line">
                  {order.items?.map((item) => (
                    <div
                      key={item.id}
                      className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-4 text-xs"
                    >
                      <div>
                        <p className="font-bold text-ink">{item.product_name}</p>
                        <p className="text-[11px] text-ink-muted mt-0.5">
                          Shop: {item.shop_name || "Assigned Shop"} · Qty: {item.quantity} × ৳{item.unit_price}
                        </p>
                      </div>
                      <span className="font-bold text-ink whitespace-nowrap">
                        ৳{item.line_total}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Order Footer */}
                <div className="p-3 sm:px-5 bg-surface-alt/20 border-t border-line flex items-center justify-between text-xs">
                  <span className="text-ink-muted">
                    Total for your shop items: ({order.seller_item_count || order.items?.length || 0} items)
                  </span>
                  <span className="font-black text-ink text-sm">
                    ৳{order.seller_subtotal}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Order Detail Modal */}
      {viewingOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-lg w-full p-6 space-y-4 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <div>
                <h3 className="text-base font-bold text-ink">
                  Order Details: {viewingOrder.order_number}
                </h3>
                <p className="text-xs text-ink-muted">
                  Status: <strong className="uppercase">{viewingOrder.status}</strong>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setViewingOrder(null)}
                className="text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            {/* Shipping Snapshot */}
            <div className="p-3.5 rounded-xl bg-surface-alt/70 border border-line text-xs space-y-1">
              <p className="font-bold text-ink uppercase tracking-wider text-[10px] text-ink-muted mb-1">
                Delivery Address Snapshot
              </p>
              <p className="font-bold text-ink">
                {viewingOrder.shipping_recipient_name || viewingOrder.customer_name}
              </p>
              <p className="text-ink-muted">
                {viewingOrder.shipping_phone || viewingOrder.phone}
              </p>
              <p className="text-ink-body">
                {viewingOrder.shipping_address_line_1 || viewingOrder.address}
                {viewingOrder.shipping_city ? `, ${viewingOrder.shipping_city}` : ""}
              </p>
            </div>

            {/* Itemized List */}
            <div>
              <p className="font-bold text-ink uppercase tracking-wider text-[10px] text-ink-muted mb-2">
                Your Shop Items
              </p>
              <div className="border border-line rounded-xl divide-y divide-line overflow-hidden">
                {viewingOrder.items?.map((item) => (
                  <div key={item.id} className="p-3 flex items-center justify-between text-xs">
                    <div>
                      <p className="font-bold text-ink">{item.product_name}</p>
                      <p className="text-[11px] text-ink-muted">
                        Qty: {item.quantity} × ৳{item.unit_price}
                      </p>
                    </div>
                    <span className="font-bold text-ink">৳{item.line_total}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-between items-center pt-3 border-t border-line text-xs font-bold">
              <span>Your Shop Subtotal</span>
              <span className="text-sm font-black text-primary">
                ৳{viewingOrder.seller_subtotal}
              </span>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setViewingOrder(null)}
                className="px-4 py-2 rounded-lg bg-surface-alt hover:bg-surface-sunken text-ink font-bold text-xs uppercase tracking-wider cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Update Status Modal */}
      {updatingOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-sm w-full p-6 space-y-4 animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <h3 className="text-base font-bold text-ink">
                Update Status: {updatingOrder.order_number}
              </h3>
              <button
                type="button"
                onClick={() => setUpdatingOrder(null)}
                className="text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <form onSubmit={handleStatusSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Select New Lifecycle Status
                </label>
                <select
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                >
                  <option value="CONFIRMED">CONFIRMED</option>
                  <option value="PROCESSING">PROCESSING</option>
                  <option value="SHIPPED">SHIPPED</option>
                  <option value="DELIVERED">DELIVERED</option>
                  <option value="CANCELLED">CANCELLED</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Status Note / Reason (optional)
                </label>
                <textarea
                  rows={2}
                  value={statusNote}
                  onChange={(e) => setStatusNote(e.target.value)}
                  placeholder="e.g. Dispatched via courier tracking #12345"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-line">
                <button
                  type="button"
                  onClick={() => setUpdatingOrder(null)}
                  className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updatingLoading}
                  className="px-5 py-2 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-all cursor-pointer"
                >
                  {updatingLoading ? "Updating..." : "Confirm Update"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
