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
import { humanizeToken } from "@/lib/admin-format";

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

// =============================================================================
// USER CREATION (Phase 1G-C)
// =============================================================================

export interface UserCreateFormValues {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  roles: string[];
}

export const EMPTY_USER_CREATE_FORM: UserCreateFormValues = {
  username: "",
  email: "",
  password: "",
  password_confirm: "",
  first_name: "",
  last_name: "",
  is_active: true,
  roles: [],
};

/**
 * Why role CODE cannot be included in a brand-new user's role set, or null.
 *
 * Mirrors checks 1 and 2 of AdminUserListAPIView.post exactly, evaluated
 * against an empty starting role set (a new account holds nothing yet): only a
 * Super Administrator may grant SUPER_ADMINISTRATOR or any other protected
 * role code. Unlike getRoleToggleLock (used on the existing-user detail page),
 * there is no "already holds it" exception — a brand-new account cannot
 * already hold anything, so that escape hatch does not apply here.
 */
export function getRoleAssignLockForCreate(
  actor: AuthUser | null | undefined,
  role: AdminRole
): string | null {
  const actorIsSuper = isSuperAdministrator(actor);
  if (role.code === SUPER_ADMINISTRATOR_CODE && !actorIsSuper) {
    return "Only a Super Administrator can grant the Super Administrator role.";
  }
  if (isProtectedRoleCode(role.code) && !actorIsSuper) {
    return `Only a Super Administrator can assign the protected role ${role.code}.`;
  }
  if (!role.is_active) {
    return "This role is inactive and cannot be assigned until it is reactivated.";
  }
  return null;
}

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

export interface UserCreateFormProps {
  values: UserCreateFormValues;
  onChange: (values: UserCreateFormValues) => void;
  onSubmit: () => void;
  onCancel: () => void;
  submitting: boolean;
  /** Backend error text, rendered verbatim above the buttons. */
  error: string | null;
  /** The signed-in operator, used to preview the role-assignment boundary. */
  actor: AuthUser | null | undefined;
  /** Role catalogue; null while loading. */
  roles: AdminRole[] | null;
  rolesError: string | null;
  /** Whether the operator holds 'roles.admin.view' at all — see canListRoles callers. */
  canListRoles: boolean;
  idPrefix: string;
}

/**
 * Create-only user form. There is no edit counterpart: AdminUserUpdateSerializer
 * accepts only { is_active, roles, reason }, so the existing user detail page
 * (userGovernance's role checklist + the activate/deactivate button) already
 * covers every field this endpoint can change after creation — nothing here is
 * duplicated for an edit mode that does not exist server-side.
 */
export function UserCreateForm({
  values,
  onChange,
  onSubmit,
  onCancel,
  submitting,
  error,
  actor,
  roles,
  rolesError,
  canListRoles,
  idPrefix,
}: UserCreateFormProps) {
  const usernameId = `${idPrefix}-username`;
  const emailId = `${idPrefix}-email`;
  const passwordId = `${idPrefix}-password`;
  const passwordConfirmId = `${idPrefix}-password-confirm`;
  const firstNameId = `${idPrefix}-first-name`;
  const lastNameId = `${idPrefix}-last-name`;
  const activeId = `${idPrefix}-active`;

  const passwordsMismatch =
    values.password.length > 0 &&
    values.password_confirm.length > 0 &&
    values.password !== values.password_confirm;

  const canSubmit =
    !submitting &&
    values.username.trim().length > 0 &&
    values.email.trim().length > 0 &&
    values.password.length > 0 &&
    values.password_confirm.length > 0 &&
    !passwordsMismatch;

  const rolesSet = React.useMemo(() => new Set(values.roles), [values.roles]);
  const toggleRole = React.useCallback(
    (code: string) => {
      onChange({
        ...values,
        roles: rolesSet.has(code)
          ? values.roles.filter((existing) => existing !== code)
          : [...values.roles, code].sort(),
      });
    },
    [onChange, values, rolesSet]
  );

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
      className="space-y-5"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={usernameId} className={FIELD_LABEL_CLASS}>
            Username <span className="text-red-600">*</span>
          </label>
          <input
            id={usernameId}
            type="text"
            required
            disabled={submitting}
            value={values.username}
            onChange={(e) => onChange({ ...values, username: e.target.value })}
            placeholder="jsmith"
            autoComplete="off"
            className={FIELD_CONTROL_CLASS}
          />
        </div>
        <div>
          <label htmlFor={emailId} className={FIELD_LABEL_CLASS}>
            Email <span className="text-red-600">*</span>
          </label>
          <input
            id={emailId}
            type="email"
            required
            disabled={submitting}
            value={values.email}
            onChange={(e) => onChange({ ...values, email: e.target.value })}
            placeholder="jsmith@example.com"
            autoComplete="off"
            className={FIELD_CONTROL_CLASS}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={passwordId} className={FIELD_LABEL_CLASS}>
            Password <span className="text-red-600">*</span>
          </label>
          <input
            id={passwordId}
            type="password"
            required
            disabled={submitting}
            value={values.password}
            onChange={(e) => onChange({ ...values, password: e.target.value })}
            autoComplete="new-password"
            className={FIELD_CONTROL_CLASS}
          />
          <p className="text-[10px] text-ink-faint mt-1">
            Validated against the platform&apos;s password policy on submit.
          </p>
        </div>
        <div>
          <label htmlFor={passwordConfirmId} className={FIELD_LABEL_CLASS}>
            Confirm password <span className="text-red-600">*</span>
          </label>
          <input
            id={passwordConfirmId}
            type="password"
            required
            disabled={submitting}
            value={values.password_confirm}
            onChange={(e) => onChange({ ...values, password_confirm: e.target.value })}
            autoComplete="new-password"
            aria-invalid={passwordsMismatch}
            className={FIELD_CONTROL_CLASS}
          />
          {passwordsMismatch && (
            <p className="text-[10px] text-red-600 mt-1">Passwords do not match.</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={firstNameId} className={FIELD_LABEL_CLASS}>
            First name
          </label>
          <input
            id={firstNameId}
            type="text"
            disabled={submitting}
            value={values.first_name}
            onChange={(e) => onChange({ ...values, first_name: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        </div>
        <div>
          <label htmlFor={lastNameId} className={FIELD_LABEL_CLASS}>
            Last name
          </label>
          <input
            id={lastNameId}
            type="text"
            disabled={submitting}
            value={values.last_name}
            onChange={(e) => onChange({ ...values, last_name: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <input
          id={activeId}
          type="checkbox"
          checked={values.is_active}
          disabled={submitting}
          onChange={(e) => onChange({ ...values, is_active: e.target.checked })}
          className="w-4 h-4 rounded border-line accent-[var(--color-primary)] cursor-pointer disabled:cursor-not-allowed"
        />
        <label htmlFor={activeId} className="text-xs font-bold text-ink cursor-pointer">
          Active
          <span className="block text-[10px] font-medium text-ink-muted">
            An inactive account cannot sign in until reactivated.
          </span>
        </label>
      </div>

      <div>
        <p className={FIELD_LABEL_CLASS}>Roles</p>
        {!canListRoles ? (
          <div className="rounded-xl border border-line bg-surface-alt/40 p-3 flex items-start gap-2">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[18px] text-ink-muted shrink-0"
            >
              info
            </span>
            <p className="text-xs text-ink-muted">
              Assigning roles at creation also needs{" "}
              <code className="font-mono text-[11px]">roles.admin.view</code> so the console
              can list the roles available to assign. The account can still be created with no
              roles.
            </p>
          </div>
        ) : rolesError ? (
          <p className="text-xs text-red-600">{rolesError}</p>
        ) : !roles ? (
          <p className="text-xs text-ink-muted">Loading the role catalogue…</p>
        ) : roles.length === 0 ? (
          <p className="text-xs text-ink-muted">No roles are defined yet.</p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
            {roles.map((role) => {
              const lock = getRoleAssignLockForCreate(actor, role);
              const checked = rolesSet.has(role.code);
              const inputId = `${idPrefix}-role-${role.id}`;
              return (
                <li key={role.id}>
                  <label
                    htmlFor={inputId}
                    className={`flex items-start gap-2.5 rounded-xl border p-3 transition-colors ${
                      lock
                        ? "border-line bg-surface-sunken/40 cursor-not-allowed"
                        : "border-line hover:bg-surface-alt cursor-pointer"
                    }`}
                  >
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={checked}
                      disabled={Boolean(lock) || submitting}
                      onChange={() => toggleRole(role.code)}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-primary)] disabled:cursor-not-allowed"
                      aria-describedby={lock ? `${inputId}-lock` : undefined}
                    />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-bold text-ink">{role.name}</span>
                        {lock && (
                          <span
                            aria-hidden="true"
                            className="material-symbols-outlined text-[14px] text-ink-muted"
                          >
                            lock
                          </span>
                        )}
                      </span>
                      <span className="block font-mono text-[10px] text-ink-muted">
                        {role.code}
                      </span>
                      {lock && (
                        <span id={`${inputId}-lock`} className="block text-[11px] mt-1 text-ink-faint">
                          {lock}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {error && (
        <p role="alert" className="text-xs font-semibold text-red-600">
          {error}
        </p>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="submit"
          disabled={!canSubmit}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Create user
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/**
 * Summarizes a role-code list for the create-confirmation modal.
 */
export function summarizeRoleCodes(codes: string[]): string {
  if (codes.length === 0) return "no roles";
  return codes.map(humanizeToken).join(", ");
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
