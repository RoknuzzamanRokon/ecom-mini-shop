"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { getSellerOrderDetail, getSellerOrders, updateSellerOrderStatus } from "@/lib/api";
import { SellerOrder, SellerOrderDetail } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import { useLatestRequest } from "@/hooks/useLatestRequest";

// Sent with every list request, so the page count always matches (BUG-024).
const ORDERS_PAGE_SIZE = 10;

const ORDER_STATUSES = [
  "ALL",
  "PENDING",
  "CONFIRMED",
  "PROCESSING",
  "SHIPPED",
  "DELIVERED",
  "CANCELLED",
];

/** The detail's address as display lines, falling back to the legacy fields. */
function deliveryAddressLines(order: SellerOrderDetail): string[] {
  return [
    order.shipping_address_line_1 || order.address,
    order.shipping_address_line_2,
    [order.shipping_area, order.shipping_city || order.city].filter(Boolean).join(", "),
    [order.shipping_state, order.shipping_postal_code].filter(Boolean).join(" "),
    order.shipping_country,
  ].filter((line): line is string => Boolean(line));
}

export default function SellerOrdersPage() {
  const [orders, setOrders] = useState<SellerOrder[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters. The search box is debounced into searchQuery, which the server
  // matches across all the seller's orders, not just this page (BUG-025).
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [searchInput, setSearchInput] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Order Details Modal. The list row has no delivery address, so the modal
  // loads the order's detail (BUG-009).
  const [viewingOrder, setViewingOrder] = useState<SellerOrder | null>(null);
  const [orderDetail, setOrderDetail] = useState<SellerOrderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  // The order the modal shows now, so a late response for another is dropped.
  const viewingNumber = useRef<string | null>(null);

  // Status Update Modal
  const [updatingOrder, setUpdatingOrder] = useState<SellerOrder | null>(null);
  const [newStatus, setNewStatus] = useState<string>("");
  const [statusNote, setStatusNote] = useState<string>("");
  const [updatingLoading, setUpdatingLoading] = useState<boolean>(false);

  // Notifications
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Only the newest request may set the list (BUG-073).
  const beginRequest = useLatestRequest();

  const fetchOrdersList = useCallback(async () => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) return;

    try {
      setLoading(true);
      const res = await getSellerOrders(
        token,
        selectedStatus !== "ALL" ? selectedStatus : undefined,
        page,
        { q: searchQuery, pageSize: ORDERS_PAGE_SIZE }
      );
      if (!isLatest()) return;
      setOrders(res.results);
      setTotalCount(res.count);
      setTotalPages(Math.max(1, Math.ceil(res.count / ORDERS_PAGE_SIZE)));
    } catch (err: any) {
      if (!isLatest()) return;
      setActionError(err.message || "Failed to load seller orders.");
    } finally {
      if (isLatest()) setLoading(false);
    }
  }, [page, selectedStatus, searchQuery, beginRequest]);

  useEffect(() => {
    fetchOrdersList();
  }, [fetchOrdersList]);

  // A new search starts from page 1, once typing pauses.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const loadOrderDetail = (order: SellerOrder) => {
    const token = getAuthToken();
    if (!token) return;
    setOrderDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    getSellerOrderDetail(order.order_number, token)
      .then((detail) => {
        if (viewingNumber.current === order.order_number) setOrderDetail(detail);
      })
      .catch((err: Error) => {
        if (viewingNumber.current === order.order_number) {
          setDetailError(err.message || "Failed to load the order details.");
        }
      })
      .finally(() => {
        if (viewingNumber.current === order.order_number) setDetailLoading(false);
      });
  };

  const openOrderDetail = (order: SellerOrder) => {
    viewingNumber.current = order.order_number;
    setViewingOrder(order);
    loadOrderDetail(order);
  };

  const closeOrderDetail = () => {
    viewingNumber.current = null;
    setViewingOrder(null);
    setOrderDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  };

  // Starts on the first allowed next status, never on the current one, which
  // the server would refuse (BUG-029).
  const handleOpenStatusModal = (order: SellerOrder) => {
    setUpdatingOrder(order);
    setNewStatus(order.allowed_transitions[0] ?? "");
    setStatusNote("");
    setActionError(null);
  };

  const handleStatusSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!updatingOrder) return;
    const token = getAuthToken();
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
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search order # or recipient..."
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          {ORDER_STATUSES.map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => {
                setSelectedStatus(st);
                setPage(1);
              }}
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
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => openOrderDetail(order)}
                      className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-xs transition-colors cursor-pointer"
                    >
                      View Details
                    </button>
                    {order.allowed_transitions.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => handleOpenStatusModal(order)}
                        className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-semibold text-xs transition-colors shadow-xs cursor-pointer"
                      >
                        Update Status
                      </button>
                    ) : (
                      order.is_multi_merchant &&
                      !isCancelled &&
                      !isDelivered && (
                        <span
                          className="text-[11px] text-ink-muted max-w-[180px] text-right"
                          title="This order also has another merchant's items, so platform operations update its status."
                        >
                          Shared order: status set by platform operations
                        </span>
                      )
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

      {totalPages > 1 && (
        <div className="bg-surface rounded-xl border border-line p-4 flex items-center justify-between text-xs">
          <span className="text-ink-muted">
            Page {page} of {totalPages} ({totalCount} orders)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1 || loading}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}

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
                onClick={closeOrderDetail}
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
              {detailLoading ? (
                <p className="text-ink-muted">Loading delivery details...</p>
              ) : detailError ? (
                <div className="flex items-center justify-between gap-3">
                  <p className="text-accent font-semibold">{detailError}</p>
                  <button
                    type="button"
                    onClick={() => loadOrderDetail(viewingOrder)}
                    className="px-2.5 py-1 rounded-md border border-line hover:bg-surface text-ink font-semibold cursor-pointer shrink-0"
                  >
                    Retry
                  </button>
                </div>
              ) : orderDetail ? (
                <>
                  <p className="font-bold text-ink">
                    {orderDetail.shipping_recipient_name || orderDetail.customer_name}
                  </p>
                  <p className="text-ink-muted">{orderDetail.shipping_phone || orderDetail.phone}</p>
                  {deliveryAddressLines(orderDetail).map((line) => (
                    <p key={line} className="text-ink-body">
                      {line}
                    </p>
                  ))}
                </>
              ) : null}
            </div>

            {/* Itemized List */}
            <div>
              <p className="font-bold text-ink uppercase tracking-wider text-[10px] text-ink-muted mb-2">
                Your Shop Items
              </p>
              <div className="border border-line rounded-xl divide-y divide-line overflow-hidden">
                {(orderDetail ?? viewingOrder).items?.map((item) => (
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
                onClick={closeOrderDetail}
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
                  {updatingOrder.allowed_transitions.map((next) => (
                    <option key={next} value={next}>
                      {next}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-ink-muted">
                  Currently {updatingOrder.status}. Only the next allowed steps are listed.
                </p>
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
                  disabled={updatingLoading || !newStatus}
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
