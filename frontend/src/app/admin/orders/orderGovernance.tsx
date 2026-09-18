"use client";

/**
 * Order Governance feature helpers (Phase 1J).
 *
 * Colocated with the /admin/orders routes, mirroring the shopGovernance.tsx /
 * productGovernance.tsx precedent — feature-local, not a generic shared
 * component. It holds:
 *   - the real Order.STATUS_CHOICES / Payment.STATUS_CHOICES labels (verified
 *     against shop/models.py),
 *   - the status-transition action catalogue and confirmation copy,
 *   - a small mutation hook shared by the list and detail pages so the
 *     "confirm -> call API -> handle result" flow is written once.
 *
 * Nothing here talks to the network directly except through admin-api.ts, and
 * nothing here decides whether a transition is actually valid — that is
 * Order.VALID_TRANSITIONS / order.can_transition_to() on the backend. The
 * catalogue below only decides which buttons are worth offering.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminOrderDetail,
  AdminOrderListItem,
  AdminOrderStatusValue,
  updateAdminOrderStatus,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/** Verbatim (value, label) pairs from Order.STATUS_CHOICES in shop/models.py (uppercase set only — the lowercase entries are a legacy alias, never written by OrderService). */
export const ORDER_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending",
  CONFIRMED: "Confirmed",
  PROCESSING: "Processing",
  SHIPPED: "Shipped",
  DELIVERED: "Delivered",
  CANCELLED: "Cancelled",
};

export const ORDER_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(ORDER_STATUS_LABELS).map(
  ([value, label]) => ({ value, label })
);

/** Verbatim (value, label) pairs from Payment.STATUS_CHOICES in shop/models.py. */
export const PAYMENT_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending",
  PROCESSING: "Processing",
  PAID: "Paid",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
  REFUNDED: "Refunded",
  PARTIALLY_REFUNDED: "Partially Refunded",
};

export const PAYMENT_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(
  PAYMENT_STATUS_LABELS
).map(([value, label]) => ({ value, label }));

export interface OrderActionDescriptor {
  /** Target status this action transitions the order to. */
  status: AdminOrderStatusValue;
  label: string;
  icon: string;
  tone: "primary" | "danger" | "default";
  destructive: boolean;
  confirmTitle: string;
  confirmMessage: (order: { order_number: string }) => string;
}

/**
 * One descriptor per reachable target status. Mirrors Order.VALID_TRANSITIONS
 * in shop/models.py: PENDING->{CONFIRMED,CANCELLED}, CONFIRMED->{PROCESSING,
 * CANCELLED}, PROCESSING->{SHIPPED,CANCELLED}, SHIPPED->{DELIVERED},
 * DELIVERED->{}, CANCELLED->{}. Labels are friendlier than the raw status
 * ("Confirm Order" rather than "Set status to CONFIRMED") since staff act on
 * these, but the payload sent is always the exact backend status value.
 */
const ACTION_DESCRIPTORS: Record<AdminOrderStatusValue, OrderActionDescriptor> = {
  CONFIRMED: {
    status: "CONFIRMED",
    label: "Confirm Order",
    icon: "check_circle",
    tone: "primary",
    destructive: false,
    confirmTitle: "Confirm Order",
    confirmMessage: (order) => `Confirm order "${order.order_number}"? This moves it to CONFIRMED.`,
  },
  PROCESSING: {
    status: "PROCESSING",
    label: "Mark Processing",
    icon: "sync",
    tone: "primary",
    destructive: false,
    confirmTitle: "Mark Order Processing",
    confirmMessage: (order) =>
      `Move order "${order.order_number}" to PROCESSING? Fulfillment work is understood to have started.`,
  },
  SHIPPED: {
    status: "SHIPPED",
    label: "Mark Shipped",
    icon: "local_shipping",
    tone: "primary",
    destructive: false,
    confirmTitle: "Mark Order Shipped",
    confirmMessage: (order) => `Move order "${order.order_number}" to SHIPPED?`,
  },
  DELIVERED: {
    status: "DELIVERED",
    label: "Mark Delivered",
    icon: "task_alt",
    tone: "primary",
    destructive: false,
    confirmTitle: "Mark Order Delivered",
    confirmMessage: (order) =>
      `Mark order "${order.order_number}" as DELIVERED? This finalizes reserved inventory into sold stock and is normally the last step in fulfillment.`,
  },
  CANCELLED: {
    status: "CANCELLED",
    label: "Cancel Order",
    icon: "cancel",
    tone: "danger",
    destructive: true,
    confirmTitle: "Cancel Order",
    confirmMessage: (order) =>
      `Cancel order "${order.order_number}"? Reserved inventory is released back to stock and any paid payment may be automatically refunded. This cannot be undone.`,
  },
};

/**
 * UI-only guidance on which target statuses to OFFER from a given current
 * status. Mirrors Order.VALID_TRANSITIONS exactly, for the list page where
 * the API only returns the row's current `status` (not `allowed_transitions`
 * — that field is detail-only). The backend independently re-validates every
 * transition via order.can_transition_to(), so a stale or incorrect entry
 * here can only hide/show a button, never approve an invalid mutation.
 */
const STATUS_RELEVANT_TARGETS: Record<string, AdminOrderStatusValue[]> = {
  PENDING: ["CONFIRMED", "CANCELLED"],
  CONFIRMED: ["PROCESSING", "CANCELLED"],
  PROCESSING: ["SHIPPED", "CANCELLED"],
  SHIPPED: ["DELIVERED"],
  DELIVERED: [],
  CANCELLED: [],
};

/**
 * Permission gate mirroring the backend exactly: StaffOrderStatusAPIView
 * requires CanUpdateStaffOrders ('orders.staff.update') for every transition
 * — unlike Shops/Products there is no narrower per-action permission to
 * split out.
 */
function isUpdatePermitted(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.ordersUpdate);
}

/**
 * List-page action set: derived from the row's current status only (no
 * `allowed_transitions` on the list serializer). Combines the cosmetic
 * status-relevance guidance with the real permission gate.
 */
export function getAvailableOrderActions(
  order: AdminOrderListItem,
  user: AuthUser | null | undefined
): OrderActionDescriptor[] {
  if (!isUpdatePermitted(user)) return [];
  const targets = STATUS_RELEVANT_TARGETS[order.status] ?? [];
  return targets.map((status) => ACTION_DESCRIPTORS[status]);
}

/**
 * Detail-page action set: prefers the server-computed `allowed_transitions`
 * over the local STATUS_RELEVANT_TARGETS mirror, since it reflects the exact
 * instant the order was fetched rather than a hardcoded copy of the model.
 */
export function getAllowedOrderActions(
  order: AdminOrderDetail,
  user: AuthUser | null | undefined
): OrderActionDescriptor[] {
  if (!isUpdatePermitted(user)) return [];
  return order.allowed_transitions
    .filter((status): status is AdminOrderStatusValue => status in ACTION_DESCRIPTORS)
    .map((status) => ACTION_DESCRIPTORS[status]);
}

/**
 * Shared "confirm -> call the real endpoint -> surface the result" flow for
 * order status transitions, used by both the list and detail pages so the
 * mutation logic (and its error handling) is written once. Mirrors
 * useShopStatusAction / useProductStatusAction exactly.
 *
 * Backend response is authoritative: on success, `onSuccess` receives exactly
 * what StaffOrderStatusAPIView returned (the full updated order) and the
 * caller decides how to merge it into its own state. On failure — including
 * a 400 because another operator already moved the order past this
 * transition (order.can_transition_to() rejects it) — the modal stays open
 * with the backend's own message; nothing here assumes success.
 */
export function useOrderStatusAction<TOrder extends { id: number; order_number: string }>(
  onSuccess: (updated: AdminOrderDetail) => void
) {
  const [pendingAction, setPendingAction] = React.useState<OrderActionDescriptor | null>(null);
  const [targetOrder, setTargetOrder] = React.useState<TOrder | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestAction = React.useCallback((order: TOrder, descriptor: OrderActionDescriptor) => {
    setTargetOrder(order);
    setPendingAction(descriptor);
    setSubmitError(null);
  }, []);

  const cancel = React.useCallback(() => {
    setPendingAction(null);
    setTargetOrder(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (note: string) => {
      if (!pendingAction || !targetOrder) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await updateAdminOrderStatus(token, targetOrder.id, {
          status: pendingAction.status,
          note: note || undefined,
        });
        onSuccess(updated);
        setPendingAction(null);
        setTargetOrder(null);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update order status."
        );
      }
    },
    [pendingAction, targetOrder, onSuccess]
  );

  return { pendingAction, targetOrder, submitError, requestAction, cancel, confirm };
}

/**
 * Page access gate, mirroring CanViewStaffOrders ('orders.staff.view', plus
 * the superuser / SUPER_ADMINISTRATOR bypass hasAnyPermission already
 * applies). Being a management user is NOT sufficient — AdminGuard only
 * establishes console eligibility.
 */
export function canViewAdminOrders(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.ordersView);
}

/** Mirrors CanUpdateStaffOrders ('orders.staff.update') exactly. */
export function canUpdateAdminOrders(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.ordersUpdate);
}

/**
 * Page-level "you may not open this module" panel. Hiding the sidebar entry
 * does not stop somebody typing the URL, so the page renders this instead of
 * its data when the operator lacks the view permission. UX courtesy only:
 * the backend would return 403 for the request regardless.
 */
export function OrderAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">
          Insufficient Permissions
        </h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Your account does not hold the permissions required to open{" "}
          <strong className="text-ink">Orders</strong>. Order tracking requires{" "}
          <code className="font-mono text-[11px]">orders.staff.view</code>. Contact a Super
          Administrator if you believe this is incorrect.
        </p>
        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}
