"use client";

/**
 * Role & Permission Governance feature helpers (Phase 1G-A).
 *
 * Colocated with the /admin/roles routes — feature-local, not a generic Phase
 * 1A shared component. It holds:
 *   - the permission gates mirroring CanViewAdminRoles / CanManageAdminRoles,
 *   - the protected-role and delegation locks that decide which controls are
 *     offered and, when one is withheld, why,
 *   - the grouped permission selector shared by role creation and role editing,
 *   - the role form shared by both,
 *   - the page-level access notice every role route renders.
 *
 * THE DELEGATION BOUNDARY IS NOT DEFINED HERE. Each permission arrives from
 * GET /api/admin/permissions/ already carrying `is_delegatable`, computed by
 * rbac.services.get_delegatable_permission_codes — the same boundary
 * get_undelegatable_permission_codes enforces on POST /api/admin/roles/ and
 * PATCH /api/admin/roles/<pk>/. This module only renders that answer. A locked
 * checkbox is a preview of a 403, never a substitute for one: the backend
 * re-validates every submitted code and would refuse regardless of what any
 * checkbox here allowed.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import type { AdminPermission, AdminPermissionCatalog, AdminRole } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { humanizeToken } from "@/lib/admin-format";

/**
 * Page access gate mirroring CanViewAdminRoles, which accepts exactly
 * 'roles.admin.view' plus the superuser / SUPER_ADMINISTRATOR bypass. Being a
 * management user is NOT sufficient — AdminGuard only establishes console
 * eligibility.
 */
export function canViewAdminRoles(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.rolesView);
}

/** Mirrors CanManageAdminRoles: 'roles.admin.manage' plus the same bypass. */
export function canManageAdminRoles(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.rolesManage);
}

/**
 * Why this role cannot be edited at all, or null when it can.
 *
 * AdminRoleDetailAPIView.patch refuses a protected role before it looks at the
 * payload, and for every caller including a Super Administrator — protection is
 * a property of the role, not of the actor. So the console shows those roles
 * read-only rather than offering an edit form that cannot succeed.
 */
export function getRoleEditLock(
  actor: AuthUser | null | undefined,
  role: AdminRole
): string | null {
  if (!canManageAdminRoles(actor)) {
    return "Editing roles requires the roles.admin.manage permission.";
  }
  if (role.is_protected) {
    return `${role.code} is a protected system role. The backend refuses to modify or delete it for any account, including Super Administrators.`;
  }
  return null;
}

/**
 * Why this role cannot be deleted, or null when it can.
 *
 * Mirrors both of AdminRoleDetailAPIView.delete's guards: protected roles are
 * refused with 403, and a role still held by active users is refused with 400.
 */
export function getRoleDeleteLock(
  actor: AuthUser | null | undefined,
  role: AdminRole
): string | null {
  const editLock = getRoleEditLock(actor, role);
  if (editLock) return editLock;

  if (role.user_count > 0) {
    return `This role is assigned to ${role.user_count} active user${
      role.user_count === 1 ? "" : "s"
    }. Reassign them first, or deactivate the role instead of deleting it.`;
  }
  return null;
}

/**
 * The role's existing grants that the operator is NOT authorized to delegate.
 *
 * Returns [] while the catalogue is still loading, so callers must not read an
 * empty result as "everything is delegatable" before the catalogue arrives.
 */
export function getUndelegatableGrants(
  role: AdminRole,
  catalog: AdminPermissionCatalog | null
): string[] {
  if (!catalog) return [];
  const delegatable = new Set(
    catalog.results.filter((permission) => permission.is_delegatable).map((p) => p.code)
  );
  return role.permissions.filter((code) => !delegatable.has(code)).sort();
}

/**
 * Why this role's PERMISSION SET specifically cannot be edited, or null.
 *
 * This is stricter than getRoleEditLock because of how the backend applies a
 * permission change: PATCH with a `permissions` list DELETES every
 * RolePermission row for the role and recreates it from the submitted set. So
 * when a role holds a grant the operator cannot delegate, both possible
 * submissions are wrong — including that code is refused with 403, and omitting
 * it silently strips a permission the operator was never authorized to control.
 *
 * Rather than pick one of those outcomes on the operator's behalf, the console
 * withholds permission editing for that role and says which grants put it out
 * of reach. Name, description and active state stay editable.
 */
export function getPermissionEditLock(
  actor: AuthUser | null | undefined,
  role: AdminRole,
  catalog: AdminPermissionCatalog | null
): string | null {
  const editLock = getRoleEditLock(actor, role);
  if (editLock) return editLock;

  const blocked = getUndelegatableGrants(role, catalog);
  if (blocked.length > 0) {
    return `This role holds ${blocked.length} permission${
      blocked.length === 1 ? "" : "s"
    } outside your delegation authority (${blocked.join(", ")}). Saving a permission change would have to drop ${
      blocked.length === 1 ? "it" : "them"
    }, so permission editing is unavailable for this role. A Super Administrator, or an operator who holds ${
      blocked.length === 1 ? "that permission" : "those permissions"
    }, can change it.`;
  }
  return null;
}

export interface PermissionResourceGroup {
  resource: string;
  permissions: AdminPermission[];
}

/**
 * Groups the catalogue by Permission.resource for the selector.
 *
 * The backend returns rows already ordered by (resource, action) —
 * Permission.Meta.ordering — so insertion order is the display order and no
 * client-side sort is needed or applied.
 */
export function groupCatalogByResource(
  permissions: AdminPermission[]
): PermissionResourceGroup[] {
  const groups = new Map<string, AdminPermission[]>();
  for (const permission of permissions) {
    const bucket = groups.get(permission.resource);
    if (bucket) bucket.push(permission);
    else groups.set(permission.resource, [permission]);
  }
  return Array.from(groups.entries()).map(([resource, group]) => ({
    resource,
    permissions: group,
  }));
}

export interface GrantedPermissionGroup {
  resource: string;
  /** Catalogue name when it is known, else just the code. */
  permissions: Array<{ code: string; name: string | null }>;
}

/**
 * Groups a role's granted permission CODES by resource for read-only display,
 * enriching each with its catalogue name when the catalogue is available.
 *
 * The catalogue is optional so the role detail page still renders its grants if
 * GET /api/admin/permissions/ fails — the grants come from the role payload
 * itself and are never reconstructed from the catalogue.
 */
export function groupGrantedPermissions(
  codes: string[],
  catalog: AdminPermissionCatalog | null
): GrantedPermissionGroup[] {
  const byCode = new Map(catalog?.results.map((permission) => [permission.code, permission]));
  const groups = new Map<string, Array<{ code: string; name: string | null }>>();

  for (const code of [...codes].sort()) {
    const known = byCode.get(code);
    const resource = known?.resource ?? (code.includes(".") ? code.slice(0, code.indexOf(".")) : code);
    const entry = { code, name: known?.name ?? null };
    const bucket = groups.get(resource);
    if (bucket) bucket.push(entry);
    else groups.set(resource, [entry]);
  }

  return Array.from(groups.entries())
    .map(([resource, permissions]) => ({ resource, permissions }))
    .sort((a, b) => a.resource.localeCompare(b.resource));
}

const LOCK_EXPLANATION = "You are not authorized to delegate this permission.";

export interface PermissionSelectorProps {
  catalog: AdminPermissionCatalog;
  /** Currently selected permission codes. */
  selected: string[];
  onChange: (codes: string[]) => void;
  /** Disables every control, e.g. while a request is in flight. */
  disabled?: boolean;
}

/**
 * The permission selector, grouped by resource.
 *
 * Permissions the operator cannot delegate are SHOWN, disabled and labelled,
 * never hidden: hiding them would make the delegation boundary invisible, and
 * an operator who cannot see that a permission exists cannot tell the
 * difference between "this platform has no such permission" and "I may not
 * grant it". Each locked row says which it is.
 */
export function PermissionSelector({
  catalog,
  selected,
  onChange,
  disabled = false,
}: PermissionSelectorProps) {
  const selectedSet = React.useMemo(() => new Set(selected), [selected]);
  const groups = React.useMemo(
    () => groupCatalogByResource(catalog.results),
    [catalog.results]
  );

  const toggle = React.useCallback(
    (code: string) => {
      onChange(
        selectedSet.has(code)
          ? selected.filter((existing) => existing !== code)
          : [...selected, code]
      );
    },
    [onChange, selected, selectedSet]
  );

  /**
   * Bulk helpers act on the DELEGATABLE rows of a group only, so "Select all"
   * can never quietly add a permission the backend would reject.
   */
  const setGroup = React.useCallback(
    (group: PermissionResourceGroup, checked: boolean) => {
      const affected = group.permissions
        .filter((permission) => permission.is_delegatable)
        .map((permission) => permission.code);
      if (checked) {
        const next = new Set(selected);
        affected.forEach((code) => next.add(code));
        onChange(Array.from(next));
      } else {
        const removal = new Set(affected);
        onChange(selected.filter((code) => !removal.has(code)));
      }
    },
    [onChange, selected]
  );

  const lockedCount = catalog.count - catalog.delegatable_count;

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <p className="text-xs text-ink-muted">
          <strong className="text-ink">{selected.length}</strong> of {catalog.count}{" "}
          permissions selected
        </p>
        {catalog.has_full_platform_access ? (
          <p className="text-[11px] text-ink-faint">
            You hold full platform access (
            <code className="font-mono">*</code>) and may delegate every permission.
          </p>
        ) : (
          <p className="text-[11px] text-ink-faint">
            {catalog.delegatable_count} delegatable · {lockedCount} outside your authority
          </p>
        )}
      </div>

      <div className="space-y-3">
        {groups.map((group) => {
          const delegatable = group.permissions.filter((p) => p.is_delegatable);
          const selectedInGroup = group.permissions.filter((p) =>
            selectedSet.has(p.code)
          ).length;
          const allDelegatableSelected =
            delegatable.length > 0 &&
            delegatable.every((permission) => selectedSet.has(permission.code));

          return (
            <fieldset
              key={group.resource}
              className="rounded-xl border border-line bg-surface-alt/30 p-3"
            >
              <legend className="flex items-center gap-2 px-1">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-ink">
                  {humanizeToken(group.resource)}
                </span>
                <span className="text-[10px] font-semibold text-ink-muted">
                  {selectedInGroup}/{group.permissions.length}
                </span>
              </legend>

              {delegatable.length > 0 && (
                <div className="flex items-center gap-2 mb-2">
                  <button
                    type="button"
                    disabled={disabled || allDelegatableSelected}
                    onClick={() => setGroup(group, true)}
                    className="text-[10px] font-bold uppercase tracking-wider text-primary hover:underline disabled:opacity-40 disabled:no-underline disabled:cursor-not-allowed cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                  >
                    Select all
                  </button>
                  <span aria-hidden="true" className="text-ink-faint text-[10px]">
                    ·
                  </span>
                  <button
                    type="button"
                    disabled={disabled || selectedInGroup === 0}
                    onClick={() => setGroup(group, false)}
                    className="text-[10px] font-bold uppercase tracking-wider text-ink-muted hover:underline disabled:opacity-40 disabled:no-underline disabled:cursor-not-allowed cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                  >
                    Clear
                  </button>
                </div>
              )}

              <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-1.5">
                {group.permissions.map((permission) => {
                  const locked = !permission.is_delegatable;
                  const inputId = `permission-${permission.id}`;
                  return (
                    <li key={permission.id}>
                      <label
                        htmlFor={inputId}
                        className={`flex items-start gap-2 rounded-lg border p-2 transition-colors ${
                          locked
                            ? "border-line-subtle bg-surface-sunken/40 cursor-not-allowed"
                            : "border-line-subtle hover:bg-surface cursor-pointer"
                        }`}
                      >
                        <input
                          id={inputId}
                          type="checkbox"
                          checked={selectedSet.has(permission.code)}
                          disabled={locked || disabled}
                          onChange={() => toggle(permission.code)}
                          aria-describedby={locked ? `${inputId}-lock` : undefined}
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-line accent-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                        />
                        <span className="min-w-0">
                          <span className="flex items-center gap-1">
                            {locked && (
                              <span
                                aria-hidden="true"
                                className="material-symbols-outlined text-[13px] text-ink-muted"
                              >
                                lock
                              </span>
                            )}
                            <span className="font-mono text-[11px] font-bold text-ink break-all">
                              {permission.code}
                            </span>
                          </span>
                          <span className="block text-[10px] text-ink-muted line-clamp-1">
                            {permission.name}
                          </span>
                          {locked && (
                            <span
                              id={`${inputId}-lock`}
                              className="block text-[10px] text-ink-faint mt-0.5"
                            >
                              {LOCK_EXPLANATION}
                            </span>
                          )}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          );
        })}
      </div>
    </div>
  );
}

export interface RoleFormValues {
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  permissions: string[];
}

export const EMPTY_ROLE_FORM: RoleFormValues = {
  code: "",
  name: "",
  description: "",
  is_active: true,
  permissions: [],
};

export function roleToFormValues(role: AdminRole): RoleFormValues {
  return {
    code: role.code,
    name: role.name,
    description: role.description,
    is_active: role.is_active,
    permissions: [...role.permissions],
  };
}

/**
 * Mirrors AdminRoleCreateSerializer.validate_code: value.strip().upper().
 * Pre-formatting the field means the operator sees the code the backend will
 * actually store. Uniqueness and the protected-code refusal stay backend-side.
 */
export function normalizeRoleCode(value: string): string {
  return value.trim().toUpperCase();
}

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

export interface RoleFormProps {
  values: RoleFormValues;
  onChange: (values: RoleFormValues) => void;
  onSubmit: () => void;
  onCancel: () => void;
  submitting: boolean;
  submitLabel: string;
  /** Backend error text, rendered verbatim above the buttons. */
  error: string | null;
  /**
   * Create exposes `code` and forces the role active (the backend hardcodes
   * is_active=True on creation); edit locks the code, because
   * AdminRoleUpdateSerializer has no code field at all, and exposes is_active.
   */
  mode: "create" | "edit";
  catalog: AdminPermissionCatalog | null;
  /**
   * Set when the permission set specifically may not be edited — see
   * getPermissionEditLock. The selector is then replaced by this explanation.
   */
  permissionLock?: string | null;
  idPrefix: string;
}

export function RoleForm({
  values,
  onChange,
  onSubmit,
  onCancel,
  submitting,
  submitLabel,
  error,
  mode,
  catalog,
  permissionLock = null,
  idPrefix,
}: RoleFormProps) {
  const codeId = `${idPrefix}-code`;
  const nameId = `${idPrefix}-name`;
  const descriptionId = `${idPrefix}-description`;
  const activeId = `${idPrefix}-active`;

  const canSubmit =
    !submitting && values.name.trim().length > 0 && (mode === "edit" || values.code.trim().length > 0);

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
          <label htmlFor={codeId} className={FIELD_LABEL_CLASS}>
            Role code {mode === "create" && <span className="text-red-600">*</span>}
          </label>
          <input
            id={codeId}
            type="text"
            required={mode === "create"}
            disabled={mode === "edit" || submitting}
            value={values.code}
            onChange={(e) => onChange({ ...values, code: normalizeRoleCode(e.target.value) })}
            placeholder="MANAGER"
            aria-describedby={`${codeId}-help`}
            className={`${FIELD_CONTROL_CLASS} font-mono`}
          />
          <p id={`${codeId}-help`} className="text-[10px] text-ink-faint mt-1">
            {mode === "edit"
              ? "A role's code is fixed after creation — the update endpoint has no code field."
              : "Upper-cased automatically. Must be unique, and cannot be a protected system code."}
          </p>
        </div>

        <div>
          <label htmlFor={nameId} className={FIELD_LABEL_CLASS}>
            Display name <span className="text-red-600">*</span>
          </label>
          <input
            id={nameId}
            type="text"
            required
            disabled={submitting}
            value={values.name}
            onChange={(e) => onChange({ ...values, name: e.target.value })}
            placeholder="Manager"
            className={FIELD_CONTROL_CLASS}
          />
        </div>
      </div>

      <div>
        <label htmlFor={descriptionId} className={FIELD_LABEL_CLASS}>
          Description
        </label>
        <textarea
          id={descriptionId}
          rows={2}
          disabled={submitting}
          value={values.description}
          onChange={(e) => onChange({ ...values, description: e.target.value })}
          placeholder="What this role is for, and who should hold it."
          className={`${FIELD_CONTROL_CLASS} resize-y`}
        />
      </div>

      {mode === "edit" && (
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
              An inactive role grants nothing and cannot be assigned, but keeps its
              definition and its existing assignments.
            </span>
          </label>
        </div>
      )}

      <div>
        <p className={FIELD_LABEL_CLASS}>Permissions</p>
        {permissionLock ? (
          <div className="rounded-xl border border-line bg-surface-alt/40 p-3 flex items-start gap-2">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[18px] text-ink-muted shrink-0"
            >
              lock
            </span>
            <p className="text-xs text-ink-muted">{permissionLock}</p>
          </div>
        ) : !catalog ? (
          <p className="text-xs text-ink-muted">Loading the permission catalogue…</p>
        ) : (
          <PermissionSelector
            catalog={catalog}
            selected={values.permissions}
            onChange={(permissions) => onChange({ ...values, permissions })}
            disabled={submitting}
          />
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
          {submitting && (
            <span className="animate-spin rounded-full h-3 w-3 border-b-2 border-current" />
          )}
          {submitLabel}
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
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so every role
 * route renders this instead of fetching when the operator lacks the view
 * permission. It is a UX courtesy only: the backend would return 403 for the
 * request regardless.
 */
export function RoleAccessNotice() {
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
          <strong className="text-ink">Roles &amp; Permissions</strong>. Role administration
          requires <code className="font-mono text-[11px]">roles.admin.view</code>. Contact a
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
