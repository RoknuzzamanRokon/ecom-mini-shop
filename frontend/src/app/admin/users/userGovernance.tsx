"use client";

/**
 * User Governance feature helpers (Phase 1G-A).
 *
 * Colocated with the /admin/users routes — feature-local, not a generic Phase
 * 1A shared component. It holds:
 *   - the permission gates mirroring CanViewAdminUsers / CanManageAdminUsers,
 *   - a client-side preview of the backend's anti-escalation rules, used only
 *     to disable controls and explain why,
 *   - the resource grouping used to display effective permissions,
 *   - the page-level access notice both routes render.
 *
 * NOTHING HERE IS A SECURITY BOUNDARY. Every rule previewed below is enforced
 * independently by AdminUserDetailAPIView.patch, which re-checks each one on
 * every request and would refuse regardless of what this file decided. The
 * preview exists so operators are not shown controls that will certainly fail,
 * and so the reason is visible before they click rather than only afterwards.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import type { AdminRole, AdminUserDetail, AdminUserListItem } from "@/lib/admin-api";
import {
  SUPER_ADMINISTRATOR_CODE,
  hasAnyPermission,
  isProtectedRoleCode,
  isSuperAdministrator,
} from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Page access gate mirroring CanViewAdminUsers, which accepts exactly
 * 'users.admin.view' plus the superuser / SUPER_ADMINISTRATOR bypass.
 * Being a management user is NOT sufficient — AdminGuard only establishes
 * console eligibility.
 */
export function canViewAdminUsers(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.usersView);
}

/** Mirrors CanManageAdminUsers: 'users.admin.manage' plus the same bypass. */
export function canManageAdminUsers(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.usersManage);
}

/**
 * Whether a TARGET account resolves to wildcard authority, read from its admin
 * payload. The signed-in operator's own answer comes from isSuperAdministrator
 * in admin-auth, which reads /api/auth/me/ instead.
 */
export function targetIsSuperAdministrator(
  target: AdminUserDetail | AdminUserListItem
): boolean {
  if (target.is_superuser) return true;
  if ("has_full_platform_access" in target && target.has_full_platform_access) return true;
  return target.roles.includes(SUPER_ADMINISTRATOR_CODE);
}

/** Username, or the full name when the account has one. */
export function userDisplayName(user: AdminUserDetail | AdminUserListItem): string {
  const full = `${user.first_name} ${user.last_name}`.trim();
  return full || user.username;
}

/**
 * Why the operator cannot modify this account AT ALL, or null when they can.
 *
 * Mirrors "Check 1" of AdminUserDetailAPIView.patch: a non-Super Administrator
 * may not touch a Super Administrator account, for any field. Returned as prose
 * so the page can state the rule instead of silently hiding the controls.
 */
export function getAccountManagementLock(
  actor: AuthUser | null | undefined,
  target: AdminUserDetail
): string | null {
  if (!canManageAdminUsers(actor)) {
    return "Managing user accounts requires the users.admin.manage permission.";
  }
  if (targetIsSuperAdministrator(target) && !isSuperAdministrator(actor)) {
    return "Only a Super Administrator can modify another Super Administrator account.";
  }
  return null;
}

/**
 * Why the operator cannot change this account's ROLE assignments, or null.
 *
 * Adds "Check 2": self-modification of roles is prohibited outright, for
 * everybody including a Super Administrator, because it is the most direct
 * self-escalation path. The backend raises 403 for it unconditionally.
 */
export function getRoleEditingLock(
  actor: AuthUser | null | undefined,
  target: AdminUserDetail
): string | null {
  const accountLock = getAccountManagementLock(actor, target);
  if (accountLock) return accountLock;

  if (actor && actor.id === target.id) {
    return "You cannot change your own role assignments. Ask another administrator to make this change.";
  }
  return null;
}

/**
 * Why one specific role cannot be toggled for this user, or null.
 *
 * Mirrors checks 3–5 of AdminUserDetailAPIView.patch:
 *   - only a Super Administrator may GRANT or REVOKE SUPER_ADMINISTRATOR;
 *   - only a Super Administrator may ASSIGN any other protected role
 *     (ADMINISTRATOR) that the user does not already hold;
 *   - role codes are resolved with is_active=True, so an inactive role cannot
 *     be assigned (the backend answers 400 "Unknown or inactive role codes").
 *
 * Revoking a non-Super protected role the user already holds is deliberately
 * NOT locked here: the backend's protected-role check only guards assignment.
 */
export function getRoleToggleLock(
  actor: AuthUser | null | undefined,
  target: AdminUserDetail,
  role: AdminRole
): string | null {
  const actorIsSuper = isSuperAdministrator(actor);
  const targetHasRole = target.roles.includes(role.code);

  if (role.code === SUPER_ADMINISTRATOR_CODE && !actorIsSuper) {
    return "Only a Super Administrator can grant or revoke the Super Administrator role.";
  }
  if (isProtectedRoleCode(role.code) && !targetHasRole && !actorIsSuper) {
    return `Only a Super Administrator can assign the protected role ${role.code}.`;
  }
  if (!role.is_active && !targetHasRole) {
    return "This role is inactive and cannot be assigned until it is reactivated.";
  }
  return null;
}

/**
 * A non-blocking warning about one role row, or null.
 *
 * Covers the one case a lock cannot express: the user already HOLDS a role that
 * has since been deactivated. AdminUserDetailAPIView.patch resolves the desired
 * role codes with is_active=True, so every save that still lists that role is
 * refused with 400 "Unknown or inactive role codes" — even a save that was only
 * meant to change a different role. Removing it is the only way forward, so the
 * checkbox stays enabled and this explains why.
 */
export function getRoleToggleWarning(
  target: AdminUserDetail,
  role: AdminRole
): string | null {
  if (!role.is_active && target.roles.includes(role.code)) {
    return "This role is inactive. The backend rejects any save that still includes it — clear it to remove the assignment.";
  }
  return null;
}

/**
 * Why deactivating this account would be refused, or null.
 *
 * The backend's last-Super-Administrator safeguard counts ACTIVE superadmins
 * across the whole platform, which this console cannot do from a single user
 * payload — so the count is deliberately not guessed here. Deactivating the
 * last one returns 400 and the confirmation dialog surfaces that message.
 */
export function getDeactivationLock(
  actor: AuthUser | null | undefined,
  target: AdminUserDetail
): string | null {
  const accountLock = getAccountManagementLock(actor, target);
  if (accountLock) return accountLock;

  if (actor && actor.id === target.id && target.is_active) {
    return "Deactivating your own account would end your own access. Ask another administrator to make this change.";
  }
  return null;
}

export interface PermissionResourceGroup {
  resource: string;
  codes: string[];
}

/**
 * Groups permission codes by their resource segment for display.
 *
 * "<resource>.<action>" is the format rbac.Permission enforces in its own
 * save(), so the prefix is a reliable grouping key. This is presentation only —
 * it never decides whether a user holds anything.
 */
export function groupPermissionCodesByResource(codes: string[]): PermissionResourceGroup[] {
  const groups = new Map<string, string[]>();
  for (const code of codes) {
    const resource = code.includes(".") ? code.slice(0, code.indexOf(".")) : code;
    const bucket = groups.get(resource);
    if (bucket) bucket.push(code);
    else groups.set(resource, [code]);
  }
  return Array.from(groups.entries())
    .map(([resource, groupCodes]) => ({ resource, codes: groupCodes.sort() }))
    .sort((a, b) => a.resource.localeCompare(b.resource));
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so both user
 * routes render this instead of fetching when the operator lacks the view
 * permission. It is a UX courtesy only: the backend would return 403 for the
 * request regardless.
 */
export function UserAccessNotice() {
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
          <strong className="text-ink">Users</strong>. User administration requires{" "}
          <code className="font-mono text-[11px]">users.admin.view</code>. Contact a Super
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
