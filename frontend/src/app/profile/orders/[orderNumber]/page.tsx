"use client";

import React, { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Order } from "@/lib/types";
import { cancelCustomerOrder, formatImageUrl, getOrderDetail } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { PRODUCT_REVIEWS_ANCHOR } from "@/components/product/ProductReviews";

const TRACK_STEPS = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"];
const CANCELLABLE_STATUSES = ["PENDING", "CONFIRMED", "PROCESSING"];

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  PENDING: { bg: "bg-warning/15", text: "text-warning", label: "Pending" },
  CONFIRMED: { bg: "bg-primary/10", text: "text-primary", label: "Confirmed" },
  PROCESSING: { bg: "bg-primary/10", text: "text-primary", label: "Processing" },
  SHIPPED: { bg: "bg-primary/10", text: "text-primary", label: "Shipped" },
  DELIVERED: { bg: "bg-success/15", text: "text-success", label: "Delivered" },
  CANCELLED: { bg: "bg-accent/10", text: "text-accent", label: "Cancelled" },
};

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function CustomerOrderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const orderNumber = params?.orderNumber as string;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Cancellation modal state
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const loadOrder = useCallback(async () => {
    if (!orderNumber) return;
    const token = getAuthToken();
    if (!token) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await getOrderDetail(orderNumber, token);
      if (!data) {
        setError("Order not found or you do not have permission to view it.");
      } else {
        setOrder(data);
      }
    } catch {
      setError("Unable to load order details. Please try again later.");
    } finally {
      setLoading(false);
    }
  }, [orderNumber, router]);

  useEffect(() => {
    loadOrder();
  }, [loadOrder]);

  const handleConfirmCancel = async () => {
    if (!order) return;
    const token = getAuthToken();
    if (!token) return;

    setIsCancelling(true);
    setCancelError(null);

    try {
      const updated = await cancelCustomerOrder(
        order.order_number,
        token,
        cancelReason.trim() || undefined
      );
      setOrder(updated);
      setShowCancelModal(false);
      setCancelReason("");
    } catch (err: any) {
      setCancelError(
        err instanceof Error
          ? err.message
          : "Failed to cancel order. Please verify that the order is still eligible for cancellation."
      );
    } finally {
      setIsCancelling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <span className="material-symbols-outlined text-[48px] text-ink-muted/50 animate-spin">
          progress_activity
        </span>
        <p className="text-sm text-ink-body mt-3">Loading order details…</p>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="bg-surface rounded-2xl border border-line p-10 text-center max-w-lg mx-auto">
        <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-accent/10 flex items-center justify-center text-accent">
          <span className="material-symbols-outlined text-[32px]">error</span>
        </div>
        <h1 className="text-lg font-bold text-ink">Order Not Found</h1>
        <p className="text-sm text-ink-muted mt-1 mb-6 leading-relaxed">
          {error || "The requested order does not exist or belongs to another customer account."}
        </p>
        <Link
          href="/profile/orders"
          className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          Back to Order History
        </Link>
      </div>
    );
  }

  const status = (order.status || "").toUpperCase();
  const isCancelled = status === "CANCELLED";
  const currentStep = TRACK_STEPS.indexOf(status);
  const statusMeta = STATUS_STYLES[status] || {
    bg: "bg-surface-alt",
    text: "text-ink-body",
    label: status,
  };
  const canCancel =
    order.can_cancel ?? CANCELLABLE_STATUSES.includes(status);

  return (
    <div className="flex flex-col gap-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Link
            href="/profile/orders"
            className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-primary transition-colors mb-2"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Back to Orders
          </Link>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-black text-ink font-mono tracking-tight">
              {order.order_number}
            </h1>
            <span
              className={`text-xs font-bold uppercase tracking-wide px-3 py-1 rounded-full ${statusMeta.bg} ${statusMeta.text}`}
            >
              {statusMeta.label}
            </span>
          </div>
          <p className="text-xs text-ink-muted mt-1">
            Placed on {formatDate(order.created_at)}
          </p>
        </div>

        {canCancel && (
          <button
            type="button"
            onClick={() => setShowCancelModal(true)}
            className="inline-flex items-center gap-1.5 self-start sm:self-auto bg-accent/10 hover:bg-accent/20 text-accent font-bold text-xs uppercase tracking-wider px-4 py-2.5 rounded-lg border border-accent/20 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">cancel</span>
            <span>Cancel Order</span>
          </button>
        )}
      </div>

      {/* Order Status Stepper or Cancelled Banner */}
      <div className="bg-surface rounded-2xl border border-line shadow-sm p-6">
        {isCancelled ? (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-accent/10 border border-accent/20 text-accent">
            <span className="material-symbols-outlined text-[28px] shrink-0">
              cancel
            </span>
            <div>
              <p className="text-sm font-bold">This order has been cancelled.</p>
              <p className="text-xs opacity-90 mt-0.5">
                All inventory reservations have been released back to stock.
              </p>
            </div>
          </div>
        ) : (
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-4">
              Delivery Progress
            </h2>
            <div className="flex items-center">
              {TRACK_STEPS.map((step, index) => {
                const reached = currentStep >= index;
                return (
                  <React.Fragment key={step}>
                    <div className="flex flex-col items-center gap-1.5 shrink-0">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors ${
                          reached
                            ? "bg-primary border-primary text-on-primary shadow-xs"
                            : "bg-surface border-line text-ink-muted"
                        }`}
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          {reached ? "check" : "radio_button_unchecked"}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] sm:text-[11px] font-bold uppercase tracking-wide text-center ${
                          reached ? "text-primary" : "text-ink-muted"
                        }`}
                      >
                        {step}
                      </span>
                    </div>
                    {index < TRACK_STEPS.length - 1 && (
                      <div
                        className={`flex-1 h-1 mx-1.5 mb-5 rounded transition-colors ${
                          currentStep > index ? "bg-primary" : "bg-line"
                        }`}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Main Content Grid: Items (Left) + Snapshot & Summary (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Items */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
            <h2 className="text-base font-bold text-ink mb-4 pb-2 border-b border-line flex items-center justify-between">
              <span>Order Items</span>
              <span className="text-xs font-semibold text-ink-muted">
                {order.items?.length || 0} line item(s)
              </span>
            </h2>

            <div className="divide-y divide-line">
              {order.items?.map((item) => (
                <div key={item.id} className="py-4 first:pt-0 last:pb-0 flex items-start gap-4">
                  <div className="w-16 h-16 rounded-xl bg-surface-alt border border-line shrink-0 overflow-hidden relative flex items-center justify-center">
                    {item.product_image ? (
                      <Image
                        src={formatImageUrl(item.product_image)}
                        alt={item.product_name}
                        fill
                        className="object-cover"
                      />
                    ) : (
                      <span className="material-symbols-outlined text-[28px] text-ink-muted/50">
                        inventory_2
                      </span>
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    {item.product_slug ? (
                      <Link
                        href={`/product/${item.product_slug}`}
                        className="text-sm font-bold text-ink hover:text-primary transition-colors block line-clamp-1"
                      >
                        {item.product_name}
                      </Link>
                    ) : (
                      <span className="text-sm font-bold text-ink block line-clamp-1">
                        {item.product_name}
                      </span>
                    )}

                    {item.shop_name && (
                      <p className="inline-flex items-center gap-1 text-xs text-ink-muted mt-0.5">
                        <span className="material-symbols-outlined text-[14px]">storefront</span>
                        <span>{item.shop_name}</span>
                      </p>
                    )}

                    <div className="flex items-center gap-3 mt-2 text-xs text-ink-body">
                      <span>Unit: <strong className="font-semibold text-ink">৳{item.unit_price ?? item.price}</strong></span>
                      <span>·</span>
                      <span>Qty: <strong className="font-semibold text-ink">{item.quantity}</strong></span>
                    </div>

                    {status === "DELIVERED" && item.product_slug && (
                      <Link
                        href={`/product/${item.product_slug}#${PRODUCT_REVIEWS_ANCHOR}`}
                        className="inline-flex items-center gap-1 mt-2 text-xs font-bold uppercase tracking-wider text-primary hover:underline"
                      >
                        <span className="material-symbols-outlined fill-active text-star text-[14px]">
                          star
                        </span>
                        Rate this product
                      </Link>
                    )}
                  </div>

                  <div className="text-right shrink-0">
                    <span className="text-base font-bold text-primary">
                      ৳{item.line_total ?? item.subtotal}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Historical Shipping Snapshot */}
          <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
            <h2 className="text-base font-bold text-ink mb-3 pb-2 border-b border-line flex items-center gap-2">
              <span className="material-symbols-outlined text-[20px] text-primary">
                local_shipping
              </span>
              <span>Shipping Information</span>
            </h2>
            <p className="text-[11px] text-ink-muted mb-4">
              Historical shipping address recorded when this order was placed.
            </p>

            <div className="bg-surface-alt/40 rounded-xl p-4 border border-line/60">
              <p className="text-sm font-bold text-ink mb-1">
                {order.shipping_recipient_name || order.customer_name || "Customer"}
              </p>
              <p className="text-xs text-ink-body leading-relaxed">
                {order.shipping_address_line_1 || order.address}
                {order.shipping_address_line_2 ? `, ${order.shipping_address_line_2}` : ""}
                {order.shipping_area ? `, ${order.shipping_area}` : ""}
                <br />
                {order.shipping_city || order.city}
                {order.shipping_state ? `, ${order.shipping_state}` : ""}
                {order.shipping_postal_code ? ` ${order.shipping_postal_code}` : ""}
                <br />
                {order.shipping_country || "Bangladesh"}
              </p>
              {(order.shipping_phone || order.phone) && (
                <p className="text-xs text-ink-muted mt-2 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">phone</span>
                  <span>{order.shipping_phone || order.phone}</span>
                </p>
              )}
            </div>
          </section>
        </div>

        {/* Right Column: Payment & Summary */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Payment Snapshot */}
          <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
            <h2 className="text-base font-bold text-ink mb-4 pb-2 border-b border-line flex items-center gap-2">
              <span className="material-symbols-outlined text-[20px] text-primary">
                payments
              </span>
              <span>Payment Details</span>
            </h2>

            <div className="space-y-3 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-ink-muted">Method</span>
                <span className="font-bold text-ink">
                  {order.payment?.payment_method || "Cash on Delivery"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-ink-muted">Payment Status</span>
                <span
                  className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                    order.payment?.is_paid
                      ? "bg-success/15 text-success"
                      : "bg-warning/15 text-warning"
                  }`}
                >
                  {order.payment?.is_paid ? "Paid" : "Unpaid / Pending"}
                </span>
              </div>
              {order.payment?.paid_at && (
                <div className="flex justify-between items-center">
                  <span className="text-ink-muted">Paid On</span>
                  <span className="text-ink">{formatDate(order.payment.paid_at)}</span>
                </div>
              )}
            </div>
          </section>

          {/* Pricing / Totals Breakdown */}
          <section className="bg-surface rounded-2xl border border-line shadow-sm p-6 flex flex-col justify-between">
            <h2 className="text-base font-bold text-ink mb-4 pb-2 border-b border-line">
              Order Summary
            </h2>

            <div className="space-y-2.5 text-xs text-ink-body mb-6">
              <div className="flex justify-between">
                <span className="text-ink-muted">Items Subtotal</span>
                <span className="font-semibold text-ink">৳{order.subtotal || order.total_amount}</span>
              </div>

              {Number(order.discount_total || 0) > 0 && (
                <div className="flex justify-between text-success">
                  <span>Discount</span>
                  <span className="font-semibold">-৳{order.discount_total}</span>
                </div>
              )}

              <div className="flex justify-between">
                <span className="text-ink-muted">Shipping Fee</span>
                <span className="font-semibold text-ink">
                  {Number(order.shipping_fee || 0) > 0 ? `৳${order.shipping_fee}` : "Free"}
                </span>
              </div>

              <div className="border-t border-line pt-3 mt-3 flex justify-between items-baseline">
                <span className="text-sm font-bold text-ink">Total Amount</span>
                <span className="text-xl font-extrabold text-primary">৳{order.total_amount}</span>
              </div>
            </div>

            <Link
              href="/"
              className="w-full text-center bg-surface-alt hover:bg-surface-sunken text-ink font-bold text-xs uppercase tracking-wider py-3 rounded-lg border border-line transition-colors"
            >
              Continue Shopping
            </Link>
          </section>
        </div>
      </div>

      {/* Cancellation Confirmation Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-md w-full p-6 space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-accent/10 text-accent flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-[24px]">
                  warning
                </span>
              </div>
              <div>
                <h3 className="text-base font-bold text-ink">Cancel Order</h3>
                <p className="text-xs text-ink-muted">
                  Order <span className="font-mono font-semibold">{order.order_number}</span>
                </p>
              </div>
            </div>

            <p className="text-xs text-ink-body leading-relaxed">
              Are you sure you want to cancel this order? Once cancelled, reserved items will be released back to the store inventory and this action cannot be undone.
            </p>

            {cancelError && (
              <div className="p-3 rounded-lg bg-accent/10 border border-accent/30 text-accent text-xs font-medium">
                {cancelError}
              </div>
            )}

            <div>
              <label
                htmlFor="detail-cancel-reason"
                className="block text-xs font-semibold text-ink-body mb-1"
              >
                Reason for cancellation (optional)
              </label>
              <textarea
                id="detail-cancel-reason"
                rows={2}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Changed my mind, found better price..."
                disabled={isCancelling}
                className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
              <button
                type="button"
                onClick={() => {
                  setShowCancelModal(false);
                  setCancelReason("");
                  setCancelError(null);
                }}
                disabled={isCancelling}
                className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
              >
                Keep Order
              </button>
              <button
                type="button"
                onClick={handleConfirmCancel}
                disabled={isCancelling}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent hover:bg-accent/90 text-white font-bold text-xs uppercase tracking-wider transition-colors disabled:opacity-60 cursor-pointer shadow-sm"
              >
                {isCancelling ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[14px]">
                      progress_activity
                    </span>
                    <span>Cancelling…</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[14px]">
                      close
                    </span>
                    <span>Confirm Cancellation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
