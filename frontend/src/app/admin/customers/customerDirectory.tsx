"use client";

/**
 * Customer Directory feature helpers (Phase 1F).
 *
 * Colocated with the /admin/customers routes — feature-local, not a generic
 * Phase 1A shared component. It holds:
 *   - the permission gate mirroring CanViewAdminCustomers,
 *   - the real CustomerProfile.GENDER_CHOICES labels,
 *   - a display-name fallback matching CustomerProfile.__str__,
 *   - the page-level access notice both routes render.
 *
 * There is deliberately no mutation helper here. AdminCustomerListAPIView and
 * AdminCustomerDetailAPIView define GET handlers only, so this module has no
 * write path to offer and none is invented.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import type { AdminCustomerDetail, AdminCustomerListItem } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Page access gate, mirroring CanViewAdminCustomers, which accepts exactly one
 * code — 'customers.admin.view' — plus the superuser / SUPER_ADMINISTRATOR
 * bypass. Being a management user is NOT sufficient: AdminGuard only
 * establishes console eligibility.
 */
export function canViewAdminCustomers(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.customersView);
}

/**
 * Verbatim (value, label) pairs from CustomerProfile.GENDER_CHOICES.
 * The model field is blank=True, so "" is a normal value, not missing data.
 */
export const CUSTOMER_GENDER_LABELS: Record<string, string> = {
  MALE: "Male",
  FEMALE: "Female",
  OTHER: "Other",
  PREFER_NOT_TO_SAY: "Prefer not to say",
};

export function genderLabel(gender: string): string {
  if (!gender) return "—";
  return CUSTOMER_GENDER_LABELS[gender] ?? gender;
}

/**
 * Mirrors CustomerProfile.__str__: display_name, else the user's full name,
 * else the username. The list serializer does not send first/last name, so the
 * middle step only applies on the detail page.
 */
export function customerDisplayName(
  customer: AdminCustomerListItem | AdminCustomerDetail
): string {
  if (customer.display_name) return customer.display_name;
  if ("first_name" in customer) {
    const full = `${customer.first_name} ${customer.last_name}`.trim();
    if (full) return full;
  }
  return customer.username;
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so both
 * customer routes render this instead of fetching when the operator lacks the
 * permission. It is a UX courtesy only: the backend would return 403 for the
 * request regardless.
 */
export function CustomerAccessNotice() {
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
          <strong className="text-ink">Customers</strong>. The customer directory requires{" "}
          <code className="font-mono text-[11px]">customers.admin.view</code>. Contact a Super
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
