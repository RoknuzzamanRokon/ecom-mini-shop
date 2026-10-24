"use client";

import React, { useId, useState } from "react";
import { Dialog } from "@/components/feedback";
import { cancelCustomerOrder } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { Order } from "@/lib/types";

/**
 * "Cancel this order?" for the order list cards and the order page: one
 * accessible dialog (BUG-094) instead of two hand-built copies. It sends the
 * cancellation itself and hands the updated order to `onCancelled`.
 */
export default function CancelOrderDialog({
  order,
  open,
  onClose,
  onCancelled,
}: {
  order: Pick<Order, "id" | "order_number">;
  open: boolean;
  onClose: () => void;
  onCancelled: (updated: Order) => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every opening starts clean (adjusted during render, not in an effect).
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setReason("");
      setError(null);
    }
  }

  const confirm = async () => {
    const token = getAuthToken();
    if (!token) return;

    setIsCancelling(true);
    setError(null);
    try {
      const updated = await cancelCustomerOrder(order.order_number, token, reason.trim() || undefined);
      onCancelled(updated);
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Failed to cancel order. Please verify that the order is still eligible for cancellation."
      );
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      dismissible={!isCancelling}
      labelledBy={titleId}
      describedBy={descriptionId}
      className="bg-surface rounded-2xl border border-line shadow-2xl max-w-md w-full p-6 space-y-4 animate-in zoom-in-95 duration-200"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-accent/10 text-accent flex items-center justify-center shrink-0">
          <span aria-hidden="true" className="material-symbols-outlined text-[24px]">
            warning
          </span>
        </div>
        <div>
          <h3 id={titleId} className="text-base font-bold text-ink">
            Cancel Order
          </h3>
          <p className="text-xs text-ink-muted">
            Order <span className="font-mono font-semibold">{order.order_number}</span>
          </p>
        </div>
      </div>

      <p id={descriptionId} className="text-xs text-ink-body leading-relaxed">
        Are you sure you want to cancel this order? Once cancelled, reserved items will be released back
        to the store inventory and this action cannot be undone.
      </p>

      {error && (
        <div role="alert" className="p-3 rounded-lg bg-accent/10 border border-accent/30 text-accent text-xs font-medium">
          {error}
        </div>
      )}

      <div>
        <label htmlFor={reasonId} className="block text-xs font-semibold text-ink-body mb-1">
          Reason for cancellation (optional)
        </label>
        <textarea
          id={reasonId}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Changed my mind, found better price..."
          disabled={isCancelling}
          className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60"
        />
      </div>

      <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
        <button
          type="button"
          onClick={onClose}
          disabled={isCancelling}
          className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
        >
          Keep Order
        </button>
        <button
          type="button"
          onClick={confirm}
          disabled={isCancelling}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent hover:bg-accent/90 text-white font-bold text-xs uppercase tracking-wider transition-colors disabled:opacity-60 cursor-pointer shadow-sm"
        >
          <span
            aria-hidden="true"
            className={`material-symbols-outlined text-[14px] ${isCancelling ? "animate-spin" : ""}`}
          >
            {isCancelling ? "progress_activity" : "close"}
          </span>
          <span>{isCancelling ? "Cancelling…" : "Confirm Cancellation"}</span>
        </button>
      </div>
    </Dialog>
  );
}
