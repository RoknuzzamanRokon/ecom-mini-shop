"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Order } from "@/lib/types";
import { cancelCustomerOrder, formatImageUrl } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

export const ACTIVE_STATUSES = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED"];
export const CANCELLABLE_STATUSES = ["PENDING", "CONFIRMED", "PROCESSING"];
const TRACK_STEPS = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"];

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-warning/15 text-warning",
  CONFIRMED: "bg-primary/10 text-primary",
  PROCESSING: "bg-primary/10 text-primary",
  SHIPPED: "bg-primary/10 text-primary",
  DELIVERED: "bg-success/15 text-success",
  CANCELLED: "bg-accent/10 text-accent",
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function OrderCard({
  order,
  showTracker = false,
  onOrderUpdated,
}: {
  order: Order;
  showTracker?: boolean;
  onOrderUpdated?: (updatedOrder: Order) => void;
}) {
  const status = (order.status || "").toUpperCase();
  const currentStep = TRACK_STEPS.indexOf(status);
  const isCancelled = status === "CANCELLED";
  const canCancel =
    order.can_cancel ?? CANCELLABLE_STATUSES.includes(status);

  // Cancellation modal state
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const handleConfirmCancel = async () => {
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
      setShowCancelModal(false);
      setCancelReason("");
      if (onOrderUpdated) {
        onOrderUpdated(updated);
      }
    } catch (err: any) {
      setCancelError(
        err instanceof Error
          ? err.message
          : "Failed to cancel order. Please try again."
      );
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className="bg-surface rounded-2xl border border-line shadow-sm overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-line bg-surface">
        <div className="min-w-0">
          <Link
            href={`/profile/orders/${order.order_number}`}
            className="text-sm font-bold text-ink font-mono hover:text-primary transition-colors inline-flex items-center gap-1.5"
          >
            <span>{order.order_number}</span>
            <span className="material-symbols-outlined text-[14px] opacity-70">
              arrow_outward
            </span>
          </Link>
          <p className="text-xs text-ink-muted">
            Placed {formatDate(order.created_at)}
            {order.total_items_count ? ` · ${order.total_items_count} item(s)` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-primary">৳{order.total_amount}</span>
          <span
            className={`text-[11px] font-bold uppercase tracking-wide px-3 py-1 rounded-full ${
              STATUS_STYLES[status] || "bg-surface-alt text-ink-body"
            }`}
          >
            {status || "UNKNOWN"}
          </span>
        </div>
      </div>

      {/* Tracker */}
      {showTracker && !isCancelled && (
        <div className="px-5 py-4 border-b border-line bg-surface-alt/30">
          <div className="flex items-center">
            {TRACK_STEPS.map((step, index) => {
              const reached = currentStep >= index;
              return (
                <React.Fragment key={step}>
                  <div className="flex flex-col items-center gap-1 shrink-0">
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center border-2 transition-colors ${
                        reached
                          ? "bg-primary border-primary text-on-primary"
                          : "bg-surface border-line text-ink-muted"
                      }`}
                    >
                      <span className="material-symbols-outlined text-[15px]">
                        {reached ? "check" : "radio_button_unchecked"}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wide ${
                        reached ? "text-primary" : "text-ink-muted"
                      }`}
                    >
                      {step}
                    </span>
                  </div>
                  {index < TRACK_STEPS.length - 1 && (
                    <div
                      className={`flex-1 h-0.5 mx-1 mb-4 rounded ${
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

      {/* Items */}
      <div className="px-5 py-4 flex flex-col gap-3">
        {order.items?.map((item) => (
          <div key={item.id} className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-lg bg-surface-alt border border-line shrink-0 flex items-center justify-center overflow-hidden relative">
              {item.product_image ? (
                <Image
                  src={formatImageUrl(item.product_image)}
                  alt={item.product_name}
                  fill
                  className="object-cover"
                />
              ) : (
                <span className="material-symbols-outlined text-[20px] text-ink-muted">
                  inventory_2
                </span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              {item.product_slug ? (
                <Link
                  href={`/product/${item.product_slug}`}
                  className="text-sm font-medium text-ink hover:text-primary transition-colors truncate block"
                >
                  {item.product_name}
                </Link>
              ) : (
                <span className="text-sm font-medium text-ink truncate block">
                  {item.product_name}
                </span>
              )}
              <p className="text-xs text-ink-muted">
                {item.shop_name ? `${item.shop_name} · ` : ""}Qty {item.quantity}
              </p>
            </div>
            <span className="text-sm font-semibold text-ink shrink-0">
              ৳{item.line_total ?? item.subtotal}
            </span>
          </div>
        ))}
      </div>

      {/* Shipping Snapshot Info */}
      {(order.shipping_address_line_1 || order.address) && (
        <div className="px-5 py-3 bg-surface-alt/50 border-t border-line">
          <p className="flex items-start gap-1.5 text-xs text-ink-muted">
            <span className="material-symbols-outlined text-[14px] shrink-0 mt-px">
              location_on
            </span>
            <span className="truncate">
              {order.shipping_address_line_1 || order.address}
              {order.shipping_city || order.city
                ? `, ${order.shipping_city || order.city}`
                : ""}
            </span>
          </p>
        </div>
      )}

      {/* Bottom Actions Bar */}
      <div className="px-5 py-3 border-t border-line flex items-center justify-between gap-3 bg-surface mt-auto">
        <Link
          href={`/profile/orders/${order.order_number}`}
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-primary hover:text-primary-hover transition-colors"
        >
          <span>View Details</span>
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>

        {canCancel && (
          <button
            type="button"
            onClick={() => setShowCancelModal(true)}
            className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wider text-accent hover:bg-accent/10 px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[15px]">cancel</span>
            <span>Cancel Order</span>
          </button>
        )}
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
              Are you sure you want to cancel this order? Once cancelled, reserved items will be released back to the store inventory.
            </p>

            {cancelError && (
              <div className="p-3 rounded-lg bg-accent/10 border border-accent/30 text-accent text-xs font-medium">
                {cancelError}
              </div>
            )}

            <div>
              <label
                htmlFor={`cancel-reason-${order.id}`}
                className="block text-xs font-semibold text-ink-body mb-1"
              >
                Reason for cancellation (optional)
              </label>
              <textarea
                id={`cancel-reason-${order.id}`}
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
