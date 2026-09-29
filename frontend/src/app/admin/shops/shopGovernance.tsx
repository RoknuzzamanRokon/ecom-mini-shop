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
  AdminSeller,
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
 * Which actions to OFFER for a shop's current status. This mirrors the source
 * statuses ShopService accepts (backend/shops/services.py), so no button leads
 * to a refused transition. The backend enforces them and answers 400
 * otherwise; this is never a security boundary. An unrecognized status falls
 * back to offering every action and lets the backend decide.
 */
function getStatusRelevantActions(status: string): AdminShopStatusAction[] {
  switch (status) {
    case "DRAFT":
      return ["approve"];
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
 * Per-action permission sets, mirroring SHOP_STATUS_ACTION_PERMISSIONS in
 * shop/admin_permissions.py: 'shops.approve' covers the review decision
 * (approve or reject); suspend and reactivate have no narrow code and need
 * 'shops.admin.manage'. This is the real security-relevant check;
 * getStatusRelevantActions above is cosmetic only.
 */
const ACTION_PERMISSIONS: Record<AdminShopStatusAction, string[]> = {
  approve: ADMIN_PERMISSIONS.shopsApprove,
  reject: ADMIN_PERMISSIONS.shopsApprove,
  suspend: ADMIN_PERMISSIONS.shopsManage,
  reactivate: ADMIN_PERMISSIONS.shopsManage,
};

function getPermittedActions(user: AuthUser | null | undefined): Set<AdminShopStatusAction> {
  return new Set<AdminShopStatusAction>(
    (Object.keys(ACTION_PERMISSIONS) as AdminShopStatusAction[]).filter((action) =>
      hasAnyPermission(user, ACTION_PERMISSIONS[action])
    )
  );
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
 * Mirrors CanCreateAdminShops ('shops.create' OR 'shops.admin.manage'), the
 * gate on POST /api/admin/shops/ (shop creation + owner assignment).
 */
export function canCreateAdminShops(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.shopsCreate);
}

/**
 * Mirrors CanUpdateAdminShops ('shops.update' OR 'shops.admin.manage'), the
 * gate on PATCH /api/admin/shops/<pk>/.
 */
export function canUpdateAdminShops(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.shopsUpdate);
}

/**
 * Why this seller can't be given a shop, or null if they can, mirroring
 * shops.services.ShopService.validate_seller_eligibility_for_creation.
 * Advisory only — the backend re-validates and is authoritative; this just
 * saves the operator a round trip for the common cases.
 */
export function shopOwnerEligibilityWarning(seller: AdminSeller): string | null {
  if (!seller.is_operational) {
    return `This seller's account is currently '${seller.status}'. Only an operational (APPROVED or ACTIVE) seller can own a shop.`;
  }
  if (seller.seller_type === "PRODUCT_OWNER") {
    return "Product Owners are not permitted to own shops under system business rules.";
  }
  if (seller.seller_type === "LIMITED_SHOP_OWNER" && seller.shops_count >= 1) {
    return "This Limited Shop Owner already owns a shop and is capped at 1.";
  }
  return null;
}

// =============================================================================
// PHONE NUMBERS
// =============================================================================

/** The main `phone` plus Shop.MAX_ADDITIONAL_PHONES (4) in shops/models.py. */
export const MAX_SHOP_PHONES = 5;

/** Shop.PHONE_MAX_LENGTH, the limit on every number. */
const SHOP_PHONE_MAX_LENGTH = 30;

/** A shop's numbers as form rows: the main `phone` first, always at least one row. */
export function shopPhonesToRows(shop: Pick<AdminShop, "phone" | "additional_phones">): string[] {
  const rows = [shop.phone, ...(shop.additional_phones ?? [])];
  return rows.length > 0 ? rows : [""];
}

/**
 * Form rows -> the API's `phone` + `additional_phones`. Blank rows are
 * dropped first, so the first filled row becomes the main number even if the
 * top row was left empty. The backend also trims and removes repeats.
 */
export function rowsToShopPhones(rows: string[]): { phone: string; additional_phones: string[] } {
  const filled = rows.map((row) => row.trim()).filter(Boolean);
  return { phone: filled[0] ?? "", additional_phones: filled.slice(1) };
}

/**
 * Editable list of shop phone numbers. The first row is the main number
 * (Shop.phone, the one public pages show); the rest are additional numbers.
 */
export function ShopPhoneListField({
  idPrefix,
  rows,
  onChange,
  disabled = false,
  hint,
}: {
  idPrefix: string;
  rows: string[];
  onChange: (rows: string[]) => void;
  disabled?: boolean;
  hint?: React.ReactNode;
}) {
  return (
    <fieldset>
      <legend className="block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5">
        Phone numbers
      </legend>
      <div className="space-y-2">
        {rows.map((row, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              id={`${idPrefix}-${index}`}
              type="tel"
              maxLength={SHOP_PHONE_MAX_LENGTH}
              disabled={disabled}
              value={row}
              onChange={(e) => onChange(rows.map((r, i) => (i === index ? e.target.value : r)))}
              placeholder="+880 1700 000000"
              aria-label={index === 0 ? "Main phone number" : `Additional phone number ${index}`}
              className="w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2"
            />
            {index === 0 ? (
              <span className="w-8 shrink-0 text-center text-[10px] font-bold uppercase tracking-wider text-ink-faint">
                Main
              </span>
            ) : (
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
                aria-label={`Remove phone number ${index + 1}`}
                className="w-8 h-8 shrink-0 inline-flex items-center justify-center rounded-lg border border-line text-ink-muted hover:text-danger hover:bg-surface-alt transition-colors cursor-pointer disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  close
                </span>
              </button>
            )}
          </div>
        ))}
      </div>
      {rows.length < MAX_SHOP_PHONES && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange([...rows, ""])}
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline cursor-pointer disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
            add
          </span>
          Add another number
        </button>
      )}
      {hint}
    </fieldset>
  );
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
