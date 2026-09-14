"use client";

/**
 * Seller Governance feature helpers (Phase 1C).
 *
 * Colocated with the /admin/sellers routes — feature-local, not a generic
 * Phase 1A shared component. It holds:
 *   - the real SellerProfile.STATUS_CHOICES / SELLER_TYPE_CHOICES labels
 *     (verified verbatim against sellers/models.py),
 *   - the lifecycle action catalogue and its confirmation copy,
 *   - the permission gate mirroring CanManageAdminSellers,
 *   - a mutation hook shared by the list and detail pages so the
 *     "confirm -> call API -> handle result" flow is written once,
 *   - the page-level access notice both routes render when the operator lacks
 *     the view permission.
 *
 * Nothing here talks to the network except through admin-api.ts, and nothing
 * here is a security boundary — the backend authorizes every mutation itself.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminSeller,
  AdminSellerStatusAction,
  updateAdminSellerStatus,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Verbatim (value, label) pairs from SellerProfile.STATUS_CHOICES in
 * sellers/models.py. AdminSellerSerializer returns only the raw `status` code —
 * no status_display — so this is the one place that must stay in sync with the
 * model if its choices ever change.
 */
export const SELLER_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending",
  UNDER_REVIEW: "Under Review",
  APPROVED: "Approved",
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
  REJECTED: "Rejected",
};

export const SELLER_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(
  SELLER_STATUS_LABELS
).map(([value, label]) => ({ value, label }));

/**
 * Verbatim (value, label) pairs from SellerProfile.SELLER_TYPE_CHOICES.
 *
 * Seller type is a BUSINESS attribute of the SellerProfile domain entity, not
 * an RBAC role and not a permission — it is only ever read from backend data
 * and never used for any authorization decision in this console.
 */
export const SELLER_TYPE_LABELS: Record<string, string> = {
  FULL_SHOP_OWNER: "Full Shop Owner",
  LIMITED_SHOP_OWNER: "Limited Shop Owner",
  PRODUCT_OWNER: "Product Owner",
};

export const SELLER_TYPE_OPTIONS: AdminSelectOption[] = Object.entries(
  SELLER_TYPE_LABELS
).map(([value, label]) => ({ value, label }));

export interface SellerActionDescriptor {
  action: AdminSellerStatusAction;
  label: string;
  icon: string;
  tone: "primary" | "danger" | "default";
  destructive: boolean;
  /** AdminSellerStatusUpdateSerializer requires a non-blank reason for these two only. */
  requiresReason: boolean;
  confirmTitle: string;
  confirmMessage: (seller: AdminSeller) => string;
}

const ACTION_DESCRIPTORS: Record<AdminSellerStatusAction, SellerActionDescriptor> = {
  approve: {
    action: "approve",
    label: "Approve",
    icon: "verified",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    confirmTitle: "Approve Seller",
    confirmMessage: (seller) =>
      `Approve "${seller.business_name}"? approve_seller() approves and then activates the account, so it becomes ACTIVE and gains its seller capabilities.`,
  },
  reject: {
    action: "reject",
    label: "Reject",
    icon: "cancel",
    tone: "danger",
    destructive: true,
    requiresReason: true,
    confirmTitle: "Reject Seller Application",
    confirmMessage: (seller) =>
      `Reject "${seller.business_name}"? The reason is stored on the profile and shown to the seller on their dashboard.`,
  },
  suspend: {
    action: "suspend",
    label: "Suspend",
    icon: "block",
    tone: "danger",
    destructive: true,
    requiresReason: true,
    confirmTitle: "Suspend Seller",
    confirmMessage: (seller) =>
      `Suspend "${seller.business_name}"? Seller operations are blocked while suspended, and the reason is shown to the seller.`,
  },
  reactivate: {
    action: "reactivate",
    label: "Reactivate",
    icon: "restart_alt",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    confirmTitle: "Reactivate Seller",
    confirmMessage: (seller) =>
      `Reactivate "${seller.business_name}"? The account will be set to ACTIVE, the suspension reason cleared, and seller capabilities restored.`,
  },
};

/**
 * Which actions make sense to OFFER for a seller's current status.
 *
 * Unlike the shop endpoint, this is not purely cosmetic for `reactivate`:
 * reactivate_seller() calls SellerProfile.activate(), which raises
 * "Only approved or suspended sellers can be activated." for any other state —
 * a plain django.core.exceptions.ValidationError that DRF does not translate.
 * Offering it from an ineligible state would therefore produce a 500 rather
 * than a clean error, so it is deliberately only offered from APPROVED and
 * SUSPENDED (including in the unknown-status fallback).
 *
 * approve / reject / suspend carry no from-state restriction in the backend.
 */
function getStatusRelevantActions(status: string): AdminSellerStatusAction[] {
  switch (status) {
    case "PENDING":
    case "UNDER_REVIEW":
      return ["approve", "reject"];
    case "APPROVED":
      return ["reactivate", "suspend"];
    case "ACTIVE":
      return ["suspend"];
    case "SUSPENDED":
      return ["reactivate"];
    case "REJECTED":
      return ["approve"];
    default:
      return ["approve", "reject", "suspend"];
  }
}

/**
 * Permission gate mirroring the backend exactly.
 *
 * AdminSellerStatusAPIView is gated by CanManageAdminSellers, which accepts
 * ONLY 'sellers.admin.manage' (plus the superuser / SUPER_ADMINISTRATOR
 * bypass). There is no per-action split here: unlike CanChangeAdminShopStatus,
 * it does not accept an approve-only permission. 'sellers.approve' and
 * 'sellers.suspend' gate the separate legacy endpoints under /api/sellers/,
 * which this console deliberately does not call — a console that fell back to
 * another privileged endpoint after a 403 would be bypassing the admin
 * authorization boundary.
 */
function getPermittedActions(user: AuthUser | null | undefined): Set<AdminSellerStatusAction> {
  if (!hasAnyPermission(user, ADMIN_PERMISSIONS.sellersManage)) {
    return new Set<AdminSellerStatusAction>();
  }
  return new Set<AdminSellerStatusAction>(["approve", "reject", "suspend", "reactivate"]);
}

/** Combines status relevance with the real permission gate. */
export function getAvailableSellerActions(
  seller: AdminSeller,
  user: AuthUser | null | undefined
): SellerActionDescriptor[] {
  const relevant = new Set(getStatusRelevantActions(seller.status));
  const permitted = getPermittedActions(user);
  return (Object.keys(ACTION_DESCRIPTORS) as AdminSellerStatusAction[])
    .filter((action) => relevant.has(action) && permitted.has(action))
    .map((action) => ACTION_DESCRIPTORS[action]);
}

/**
 * Page access gate, mirroring CanViewAdminSellers
 * ('sellers.admin.manage' OR 'sellers.view'). Being a management user is NOT
 * sufficient — AdminGuard only establishes console eligibility.
 */
export function canViewAdminSellers(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.sellersView);
}

/**
 * Shared "confirm -> call the real endpoint -> surface the result" flow for
 * seller lifecycle transitions, used by both the list and detail pages.
 *
 * The backend response is authoritative: on success `onSuccess` receives
 * exactly what the API returned and the caller decides how to merge it. On
 * failure the modal stays open showing the backend's own message — nothing
 * here assumes success, retries elsewhere, or renders a status the backend
 * did not confirm.
 */
export function useSellerStatusAction(onSuccess: (updated: AdminSeller) => void) {
  const [pendingAction, setPendingAction] = React.useState<SellerActionDescriptor | null>(null);
  const [targetSeller, setTargetSeller] = React.useState<AdminSeller | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestAction = React.useCallback(
    (seller: AdminSeller, descriptor: SellerActionDescriptor) => {
      setTargetSeller(seller);
      setPendingAction(descriptor);
      setSubmitError(null);
    },
    []
  );

  const cancel = React.useCallback(() => {
    setPendingAction(null);
    setTargetSeller(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!pendingAction || !targetSeller) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await updateAdminSellerStatus(token, targetSeller.id, {
          action: pendingAction.action,
          reason: pendingAction.requiresReason ? reason : undefined,
        });
        onSuccess(updated);
        setPendingAction(null);
        setTargetSeller(null);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update seller status."
        );
      }
    },
    [pendingAction, targetSeller, onSuccess]
  );

  return { pendingAction, targetSeller, submitError, requestAction, cancel, confirm };
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so both
 * seller routes render this instead of fetching when the operator lacks the
 * view permission. It is a UX courtesy only: the backend would return 403 for
 * the request regardless.
 */
export function SellerAccessNotice() {
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
          <strong className="text-ink">Sellers</strong>. Seller governance requires{" "}
          <code className="font-mono text-[11px]">sellers.view</code> or{" "}
          <code className="font-mono text-[11px]">sellers.admin.manage</code>. Contact a
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
