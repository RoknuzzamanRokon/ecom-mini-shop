"use client";

/**
 * Shop Governance feature helpers (Phase 1B).
 *
 * Colocated with the /admin/shops routes — this is feature-local, not a
 * generic Phase 1A shared component. It holds:
 *   - the real Shop.STATUS_CHOICES labels (verified against shops/models.py),
 *   - the status-transition action catalogue and confirmation copy,
 *   - a small mutation hook shared by the list and detail pages so the
 *     "confirm -> call API -> handle result" flow is written once.
 *
 * Nothing here talks to the network directly except through admin-api.ts.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminShop,
  AdminShopStatusAction,
  updateAdminShopStatus,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Verbatim (value, label) pairs from Shop.STATUS_CHOICES in shops/models.py.
 * Kept here rather than derived, since the API never returns the human label —
 * only the raw `status` code — so this is the one place that must stay in
 * sync with the backend model if its choices ever change.
 */
export const SHOP_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  PENDING: "Pending Review",
  APPROVED: "Approved",
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
  REJECTED: "Rejected",
};

export const SHOP_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(SHOP_STATUS_LABELS).map(
  ([value, label]) => ({ value, label })
);

export interface ShopActionDescriptor {
  action: AdminShopStatusAction;
  label: string;
  icon: string;
  tone: "primary" | "danger" | "default";
  destructive: boolean;
  /** Backend requires a non-blank reason for 'reject' and 'suspend' only. */
  requiresReason: boolean;
  confirmTitle: string;
  confirmMessage: (shop: AdminShop) => string;
}

const ACTION_DESCRIPTORS: Record<AdminShopStatusAction, ShopActionDescriptor> = {
  approve: {
    action: "approve",
    label: "Approve",
    icon: "check_circle",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    confirmTitle: "Approve Shop",
    confirmMessage: (shop) =>
      `Approve "${shop.name}"? The shop will become ACTIVE and visible to customers.`,
  },
  reject: {
    action: "reject",
    label: "Reject",
    icon: "cancel",
    tone: "danger",
    destructive: true,
    requiresReason: true,
    confirmTitle: "Reject Shop",
    confirmMessage: (shop) =>
      `Reject "${shop.name}"? The seller will see this reason, and the shop will not go live.`,
  },
  suspend: {
    action: "suspend",
    label: "Suspend",
    icon: "block",
    tone: "danger",
    destructive: true,
    requiresReason: true,
    confirmTitle: "Suspend Shop",
    confirmMessage: (shop) =>
      `Suspend "${shop.name}"? Its products will no longer be publicly visible until it is reactivated.`,
  },
  reactivate: {
    action: "reactivate",
    label: "Reactivate",
    icon: "restart_alt",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    confirmTitle: "Reactivate Shop",
    confirmMessage: (shop) => `Reactivate "${shop.name}"? The shop will become ACTIVE again.`,
  },
};

/**
 * UI-only guidance on which actions make sense to OFFER for a shop's current
 * status (e.g. hide "Reactivate" on a shop that isn't suspended). The backend
 * status endpoint has no from-state restriction of its own — any action is
 * accepted from any status — so this is purely to avoid a confusing button,
 * never a security boundary. An unrecognized status falls back to offering
 * every action, since hiding all of them for an unknown state would be an
 * arbitrary UI opinion the backend does not share.
 */
function getStatusRelevantActions(status: string): AdminShopStatusAction[] {
  switch (status) {
    case "DRAFT":
    case "PENDING":
      return ["approve", "reject"];
    case "APPROVED":
    case "ACTIVE":
      return ["suspend"];
    case "SUSPENDED":
      return ["reactivate"];
    case "REJECTED":
      return ["approve"];
    default:
      return ["approve", "reject", "suspend", "reactivate"];
  }
}

/**
 * Permission gate mirroring the backend exactly:
 *   - AdminShopStatusAPIView requires CanChangeAdminShopStatus to enter at all
 *     (shops.admin.manage OR shops.approve).
 *   - Inside _update_status, only 'approve' is allowed without
 *     shops.admin.manage; reject/suspend/reactivate all require it.
 * This is the real security-relevant check; getStatusRelevantActions above is
 * cosmetic only.
 */
function getPermittedActions(user: AuthUser | null | undefined): Set<AdminShopStatusAction> {
  const permitted = new Set<AdminShopStatusAction>();
  if (hasAnyPermission(user, ADMIN_PERMISSIONS.shopsApprove)) permitted.add("approve");
  if (hasAnyPermission(user, ADMIN_PERMISSIONS.shopsManage)) {
    permitted.add("reject");
    permitted.add("suspend");
    permitted.add("reactivate");
  }
  return permitted;
}

/** Combines status relevance (cosmetic) with the real permission gate. */
export function getAvailableShopActions(
  shop: AdminShop,
  user: AuthUser | null | undefined
): ShopActionDescriptor[] {
  const relevant = new Set(getStatusRelevantActions(shop.status));
  const permitted = getPermittedActions(user);
  return (Object.keys(ACTION_DESCRIPTORS) as AdminShopStatusAction[])
    .filter((action) => relevant.has(action) && permitted.has(action))
    .map((action) => ACTION_DESCRIPTORS[action]);
}

/**
 * Shared "confirm -> call the real endpoint -> surface the result" flow for
 * shop status transitions, used by both the list and detail pages so the
 * mutation logic (and its error handling) is written once.
 *
 * Backend response is authoritative: on success, `onSuccess` receives exactly
 * what the API returned and the caller decides how to merge it into its own
 * state. On failure the modal stays open with the backend's own message —
 * nothing here ever assumes success or displays a status the backend rejected.
 */
export function useShopStatusAction(onSuccess: (updated: AdminShop) => void) {
  const [pendingAction, setPendingAction] = React.useState<ShopActionDescriptor | null>(null);
  const [targetShop, setTargetShop] = React.useState<AdminShop | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestAction = React.useCallback((shop: AdminShop, descriptor: ShopActionDescriptor) => {
    setTargetShop(shop);
    setPendingAction(descriptor);
    setSubmitError(null);
  }, []);

  const cancel = React.useCallback(() => {
    setPendingAction(null);
    setTargetShop(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!pendingAction || !targetShop) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await updateAdminShopStatus(token, targetShop.id, {
          action: pendingAction.action,
          reason: pendingAction.requiresReason ? reason : undefined,
        });
        onSuccess(updated);
        setPendingAction(null);
        setTargetShop(null);
      } catch (err) {
        // Never assume success and never bypass a 403 — leave the modal open
        // showing exactly what the backend said, so the operator can adjust
        // the reason or cancel explicitly.
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update shop status."
        );
      }
    },
    [pendingAction, targetShop, onSuccess]
  );

  return { pendingAction, targetShop, submitError, requestAction, cancel, confirm };
}

/**
 * Page access gate, mirroring CanViewAdminShops
 * ('shops.admin.manage' OR 'shops.view'). Being a management user is NOT
 * sufficient — AdminGuard only establishes console eligibility.
 */
export function canViewAdminShops(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.shopsView);
}

/**
 * Mirrors CanManageAdminShops exactly: 'shops.admin.manage' plus the
 * superuser / SUPER_ADMINISTRATOR bypass. This is the gate for POST
 * /api/admin/shops/ (Phase 1H shop creation + owner assignment) —
 * AdminShopListAPIView.post uses the identical permission class. Holding
 * only 'shops.approve' (the narrower shopsApprove set) is NOT enough, exactly
 * as it is not enough for reject/suspend/reactivate above.
 */
export function canManageAdminShops(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.shopsManage);
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so the
 * shop creation route renders this instead of its form when the operator
 * lacks the view permission. It is a UX courtesy only: the backend would
 * return 403 for the request regardless.
 */
export function ShopAccessNotice() {
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
          <strong className="text-ink">Shops</strong>. Shop governance requires{" "}
          <code className="font-mono text-[11px]">shops.view</code> or{" "}
          <code className="font-mono text-[11px]">shops.admin.manage</code>. Contact a
          Super Administrator if you believe this is incorrect.
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
