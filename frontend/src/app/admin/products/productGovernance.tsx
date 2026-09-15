"use client";

/**
 * Product Governance feature helpers (Phase 1D).
 *
 * Colocated with the /admin/products routes — feature-local, not a generic
 * Phase 1A shared component. It holds:
 *   - the real Product.STATUS_CHOICES labels (verbatim from shop/models.py),
 *   - the lifecycle action catalogue and its confirmation copy,
 *   - the GRANULAR permission gates mirroring AdminProductStatusAPIView,
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
  AdminProduct,
  AdminProductStatusAction,
  updateAdminProductStatus,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Verbatim (value, label) pairs from Product.STATUS_CHOICES in shop/models.py.
 * AdminProductSerializer returns only the raw `status` code — no status_display —
 * so this is the one place that must stay in sync with the model.
 */
export const PRODUCT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  PUBLISHED: "Published",
  UNPUBLISHED: "Unpublished",
};

export const PRODUCT_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(
  PRODUCT_STATUS_LABELS
).map(([value, label]) => ({ value, label }));

export interface ProductActionDescriptor {
  action: AdminProductStatusAction;
  label: string;
  icon: string;
  tone: "primary" | "danger" | "default";
  destructive: boolean;
  /** AdminProductStatusUpdateSerializer requires a non-blank reason for 'reject' only. */
  requiresReason: boolean;
  /** The OR-set of permission codes the backend accepts for THIS action. */
  permissions: string[];
  confirmTitle: string;
  confirmMessage: (product: AdminProduct) => string;
}

const ACTION_DESCRIPTORS: Record<AdminProductStatusAction, ProductActionDescriptor> = {
  approve: {
    action: "approve",
    label: "Approve",
    icon: "verified",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    permissions: ADMIN_PERMISSIONS.productsApprove,
    confirmTitle: "Approve Product",
    confirmMessage: (product) =>
      `Approve "${product.name}"? The listing moves to APPROVED and any previous rejection reason is cleared. Approving does not publish it — it stays out of the public catalog until it is published.`,
  },
  reject: {
    action: "reject",
    label: "Reject",
    icon: "cancel",
    tone: "danger",
    destructive: true,
    requiresReason: true,
    permissions: ADMIN_PERMISSIONS.productsReject,
    confirmTitle: "Reject Product",
    confirmMessage: (product) =>
      `Reject "${product.name}"? The listing moves to REJECTED and leaves the public catalog. The reason is stored on the product and shown to the seller.`,
  },
  publish: {
    action: "publish",
    label: "Publish",
    icon: "public",
    tone: "primary",
    destructive: false,
    requiresReason: false,
    permissions: ADMIN_PERMISSIONS.productsPublish,
    confirmTitle: "Publish Product",
    confirmMessage: (product) =>
      `Publish "${product.name}"? The listing becomes PUBLISHED and is activated. The backend refuses this if the owning shop is not approved/active or the seller is not operational.`,
  },
  unpublish: {
    action: "unpublish",
    label: "Unpublish",
    icon: "visibility_off",
    tone: "danger",
    destructive: true,
    requiresReason: false,
    // No narrow 'products.unpublish' permission exists in seed_rbac.py, and the
    // backend restricts this action to full product management. Do not widen.
    permissions: ADMIN_PERMISSIONS.productsManage,
    confirmTitle: "Unpublish Product",
    confirmMessage: (product) =>
      `Unpublish "${product.name}"? The listing moves to UNPUBLISHED and is withdrawn from the public catalog. It keeps its approval and can be published again later.`,
  },
};

/**
 * Which actions make sense to OFFER for a product's current status.
 *
 * AdminProductStatusAPIView applies no from-state guard at all (the only
 * lifecycle validation is publish's shop/seller operational check), so this is
 * a UX filter rather than a correctness requirement — it keeps the console from
 * advertising transitions that are meaningless for the current state.
 *
 * DRAFT is deliberately empty: a draft is the seller's own unsubmitted work, so
 * there is nothing for a moderator to decide yet. Everything from SUBMITTED
 * onward is a moderation state and offers the transitions that advance or
 * reverse it.
 */
function getStatusRelevantActions(status: string): AdminProductStatusAction[] {
  switch (status) {
    case "DRAFT":
      return [];
    case "SUBMITTED":
      return ["approve", "reject"];
    case "APPROVED":
      return ["publish", "reject"];
    case "REJECTED":
      return ["approve"];
    case "PUBLISHED":
      return ["unpublish", "reject"];
    case "UNPUBLISHED":
      return ["publish", "reject"];
    default:
      return ["approve", "reject"];
  }
}

/**
 * Per-action permission gate mirroring AdminProductStatusAPIView._update_status.
 *
 * This is the important difference from the shop and seller modules: the
 * product status endpoint does NOT use a single manage permission. Entry is
 * gated by CanChangeAdminProductStatus (any one of the four codes), and the
 * view body then requires the specific code for the action being performed:
 *
 *   approve   -> products.approve   OR products.admin.manage
 *   reject    -> products.reject    OR products.admin.manage
 *   publish   -> products.publish   OR products.admin.manage
 *   unpublish ->                       products.admin.manage   (only)
 *
 * So an OPERATION_MANAGER (approve/reject/publish, no admin.manage) sees three
 * of the four actions and never sees Unpublish.
 */
export function canPerformProductAction(
  user: AuthUser | null | undefined,
  action: AdminProductStatusAction
): boolean {
  return hasAnyPermission(user, ACTION_DESCRIPTORS[action].permissions);
}

/** Combines status relevance with the real per-action permission gate. */
export function getAvailableProductActions(
  product: AdminProduct,
  user: AuthUser | null | undefined
): ProductActionDescriptor[] {
  return getStatusRelevantActions(product.status)
    .filter((action) => canPerformProductAction(user, action))
    .map((action) => ACTION_DESCRIPTORS[action]);
}

/**
 * Page access gate, mirroring CanViewAdminProducts
 * ('products.admin.manage' OR 'products.view'). Being a management user is NOT
 * sufficient — AdminGuard only establishes console eligibility.
 */
export function canViewAdminProducts(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.productsView);
}

/**
 * Shared "confirm -> call the real endpoint -> surface the result" flow for
 * product lifecycle transitions, used by both the list and detail pages.
 *
 * The backend response is authoritative: on success `onSuccess` receives
 * exactly what the API returned and the caller decides how to merge it. On
 * failure the modal stays open showing the backend's own message — including
 * the 403 raised for an action the operator's narrow permission does not cover
 * and the 400 raised when a product's shop or seller is not operational.
 * Nothing here assumes success, retries against another endpoint, or renders a
 * status the backend did not confirm.
 */
export function useProductStatusAction(onSuccess: (updated: AdminProduct) => void) {
  const [pendingAction, setPendingAction] = React.useState<ProductActionDescriptor | null>(null);
  const [targetProduct, setTargetProduct] = React.useState<AdminProduct | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestAction = React.useCallback(
    (product: AdminProduct, descriptor: ProductActionDescriptor) => {
      setTargetProduct(product);
      setPendingAction(descriptor);
      setSubmitError(null);
    },
    []
  );

  const cancel = React.useCallback(() => {
    setPendingAction(null);
    setTargetProduct(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!pendingAction || !targetProduct) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await updateAdminProductStatus(token, targetProduct.id, {
          action: pendingAction.action,
          reason: pendingAction.requiresReason ? reason : undefined,
        });
        onSuccess(updated);
        setPendingAction(null);
        setTargetProduct(null);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update product status."
        );
      }
    },
    [pendingAction, targetProduct, onSuccess]
  );

  return { pendingAction, targetProduct, submitError, requestAction, cancel, confirm };
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so both
 * product routes render this instead of fetching when the operator lacks the
 * view permission. It is a UX courtesy only: the backend would return 403 for
 * the request regardless.
 */
export function ProductAccessNotice() {
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
          <strong className="text-ink">Products</strong>. Catalog governance requires{" "}
          <code className="font-mono text-[11px]">products.view</code> or{" "}
          <code className="font-mono text-[11px]">products.admin.manage</code>. Contact a
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
