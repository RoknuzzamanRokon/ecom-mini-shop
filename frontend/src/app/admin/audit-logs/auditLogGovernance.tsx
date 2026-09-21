"use client";

/**
 * Audit Log feature helpers (Phase 2I).
 *
 * Colocated with the /admin/audit-logs route — feature-local, not a generic
 * Phase 1A shared component. It holds:
 *   - the permission gate mirroring CanViewAdminAuditLogs,
 *   - the real target_type vocabulary AuditService writes,
 *   - an actor-name fallback matching AuditLog.__str__,
 *   - a reason accessor matching AuditLog.reason,
 *   - an action -> badge tone map,
 *   - the page-level access notice.
 *
 * There is deliberately no mutation helper here, and there cannot be one:
 * AdminAuditLogListAPIView sets http_method_names = ["get", "head", "options"],
 * so POST/PUT/PATCH/DELETE are rejected at the view before any permission is
 * consulted. Audit logs are immutable by design.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import type { AdminAuditLog } from "@/lib/admin-api";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AdminStatusTone } from "@/components/admin/shared/AdminStatusBadge";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Page access gate, mirroring CanViewAdminAuditLogs.
 *
 * That class accepts 'audit.view', 'audit.admin.view', 'users.admin.view' or
 * 'roles.admin.view', plus the superuser / SUPER_ADMINISTRATOR bypass. Only the
 * last two are in ADMIN_PERMISSIONS.auditView, because the first two are absent
 * from seed_rbac's PERMISSIONS_DATA and so cannot be held by any real user —
 * gating on them would hide the module from everyone but superusers. Being a
 * management user is NOT sufficient: AdminGuard only establishes console
 * eligibility.
 */
export function canViewAdminAuditLogs(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.auditView);
}

/**
 * The target types the backend actually writes.
 *
 * AuditService.log derives target_type as `target.__class__.__name__`
 * (audit/services.py:35) — there are no model choices to mirror, so this list
 * was built by resolving every `target=` argument at every `AuditService.log`
 * call site to its model class. The Django-admin mixin's generic `target=obj`
 * (audit/admin_mixins.py:122,158) resolves to SellerProfile or Shop, both
 * already listed.
 *
 * The filter is the only thing that depends on this list. A target_type outside
 * it still renders correctly in the table, because the column prints whatever
 * the API returns rather than looking it up here.
 */
export const AUDIT_TARGET_TYPE_LABELS: Record<string, string> = {
  Address: "Address",
  Category: "Category",
  CustomerProfile: "Customer Profile",
  Order: "Order",
  Payment: "Payment",
  PointTransaction: "Point Transaction",
  Product: "Product",
  Refund: "Refund",
  Review: "Review",
  Role: "Role",
  SellerProfile: "Seller",
  Shop: "Shop",
  User: "User",
};

export const AUDIT_TARGET_TYPE_OPTIONS: AdminSelectOption[] = Object.entries(
  AUDIT_TARGET_TYPE_LABELS
).map(([value, label]) => ({ value, label }));

export function auditTargetTypeLabel(targetType: string): string {
  if (!targetType) return "—";
  return AUDIT_TARGET_TYPE_LABELS[targetType] ?? targetType;
}

/**
 * Mirrors AuditLog.__str__ (audit/models.py:84): the actor's name, or "System"
 * when actor is NULL.
 *
 * actor is `on_delete=SET_NULL`, so a null actor means either a genuinely
 * system-initiated action or a since-deleted account. The record deliberately
 * survives the user, which is why this never renders an empty cell.
 */
export function auditActorName(log: AdminAuditLog): string {
  if (!log.actor) return "System";
  return log.actor.full_name || log.actor.username || log.actor.email || "System";
}

/**
 * Mirrors AuditLog.reason (audit/models.py:70): the 'reason' key inside the
 * metadata payload, which AuditService.log writes there for every governance
 * action that requires one. Returns null rather than "N/A" so the caller can
 * choose its own empty rendering.
 */
export function auditLogReason(log: AdminAuditLog): string | null {
  const reason = log.metadata?.reason;
  if (typeof reason !== "string") return null;
  const trimmed = reason.trim();
  return trimmed ? trimmed : null;
}

/**
 * Action codes carry no status vocabulary, so AdminStatusBadge's own STATUS_TONES
 * map does not apply — it would resolve almost every action to "neutral". Tone is
 * derived from the action's verb instead, matched against the real vocabulary
 * written across the backend (INVENTORY_RESERVED, ADMIN_SELLER_SUSPEND,
 * PAYMENT_FAILED, PRODUCT_DELETED, ORDER_CREATED, …). Substring matching keeps
 * the dynamically built codes working too — shop/admin_views.py composes
 * f"ADMIN_PRODUCT_{action.upper()}" and two siblings do the same — so a newly
 * added verb degrades to "neutral" rather than breaking.
 */
const ACTION_TONE_RULES: Array<[string, AdminStatusTone]> = [
  ["DELETE", "danger"],
  ["REJECT", "danger"],
  ["SUSPEND", "danger"],
  ["FAIL", "danger"],
  ["CANCEL", "warning"],
  ["REFUND", "accent"],
  ["APPROVE", "success"],
  ["REACTIVATE", "success"],
  ["PUBLISH", "success"],
  ["SUCCESS", "success"],
  ["DELIVERED", "success"],
  ["CREATE", "info"],
  ["UPDATE", "info"],
  ["ADJUST", "info"],
  ["RESERVE", "info"],
  ["RELEASE", "info"],
  ["CREDIT", "info"],
  ["PROMOTED", "info"],
  ["SET", "info"],
];

export function auditActionTone(action: string): AdminStatusTone {
  const code = (action || "").toUpperCase();
  for (const [needle, tone] of ACTION_TONE_RULES) {
    if (code.includes(needle)) return tone;
  }
  return "neutral";
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so the route
 * renders this instead of fetching when the operator lacks the permission. It is
 * a UX courtesy only: the backend would return 403 for the request regardless.
 */
export function AuditLogAccessNotice() {
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
          Your account does not hold the permission required to open{" "}
          <strong className="text-ink">Audit Logs</strong>. The governance history requires{" "}
          <code className="font-mono text-[11px]">users.admin.view</code> or{" "}
          <code className="font-mono text-[11px]">roles.admin.view</code>. Contact a Super
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
