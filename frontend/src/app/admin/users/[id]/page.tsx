"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminRole,
  AdminUserDetail,
  getAdminRoles,
  getAdminUserDetail,
  updateAdminUser,
} from "@/lib/admin-api";
import { formatDateTime, humanizeToken } from "@/lib/admin-format";
import { hasAnyPermission, isProtectedRoleCode } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import {
  UserAccessNotice,
  canViewAdminUsers,
  getAccountManagementLock,
  getDeactivationLock,
  getRoleEditingLock,
  getRoleToggleLock,
  getRoleToggleWarning,
  groupPermissionCodesByResource,
  targetIsSuperAdministrator,
  userDisplayName,
} from "../userGovernance";
import { canManageAdminSellers } from "../../sellers/sellerGovernance";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-40 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value}</dd>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading user detail">
      <div className="h-6 w-40 bg-surface-alt animate-pulse rounded-md" />
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[0, 1].map((i) => (
          <div key={i} className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
            <div className="h-4 w-32 bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-full bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-3/4 bg-surface-alt animate-pulse rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Which confirmation the page is currently showing, if any. */
type PendingChange =
  | { kind: "activation"; nextActive: boolean }
  | { kind: "roles"; desiredRoles: string[]; added: string[]; removed: string[] };

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const userId = params.id;
  const { user: actor } = useAuth();

  const canView = canViewAdminUsers(actor);
  const canListRoles = hasAnyPermission(actor, ADMIN_PERMISSIONS.rolesView);

  const [target, setTarget] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [rolesError, setRolesError] = useState<string | null>(null);

  /** Draft role selection, seeded from the server payload on every (re)load. */
  const [draftRoles, setDraftRoles] = useState<string[]>([]);
  const [pendingChange, setPendingChange] = useState<PendingChange | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchUser = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminUserDetail(token, userId);
      setTarget(data);
      setDraftRoles([...data.roles].sort());
    } catch (err) {
      setTarget(null);
      setError(err instanceof Error ? err : new Error("Failed to load user."));
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (!canView) return;
    fetchUser();
  }, [canView, fetchUser]);

  /**
   * The assignable-role catalogue. Requires 'roles.admin.view' — a user
   * administrator without it still sees the assigned roles from the user
   * payload, but cannot be offered an assignment editor, because the console
   * has no way to enumerate what exists to assign.
   */
  useEffect(() => {
    if (!canView || !canListRoles) return;
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getAdminRoles(token)
      .then((data) => {
        if (!cancelled) {
          setRoles(data);
          setRolesError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setRoles([]);
          setRolesError(
            err instanceof AdminApiError ? err.message : "Failed to load the role catalogue."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canView, canListRoles]);

  const accountLock = target ? getAccountManagementLock(actor, target) : null;
  const roleEditingLock = target ? getRoleEditingLock(actor, target) : null;
  const deactivationLock = target ? getDeactivationLock(actor, target) : null;

  const assignedSet = useMemo(() => new Set(target?.roles ?? []), [target]);
  const draftSet = useMemo(() => new Set(draftRoles), [draftRoles]);

  const roleDiff = useMemo(() => {
    const added = draftRoles.filter((code) => !assignedSet.has(code)).sort();
    const removed = [...assignedSet].filter((code) => !draftSet.has(code)).sort();
    return { added, removed };
  }, [draftRoles, assignedSet, draftSet]);

  const rolesDirty = roleDiff.added.length > 0 || roleDiff.removed.length > 0;

  const toggleRole = useCallback((code: string) => {
    setDraftRoles((current) =>
      current.includes(code)
        ? current.filter((existing) => existing !== code)
        : [...current, code].sort()
    );
  }, []);

  const resetRoleDraft = useCallback(() => {
    if (target) setDraftRoles([...target.roles].sort());
  }, [target]);

  const confirmChange = useCallback(
    async (reason: string) => {
      if (!pendingChange || !target) return;
      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await updateAdminUser(token, target.id, {
          reason,
          ...(pendingChange.kind === "activation"
            ? { is_active: pendingChange.nextActive }
            : { roles: pendingChange.desiredRoles }),
        });
        // The response is authoritative — never assume the change we asked for.
        setTarget(updated);
        setDraftRoles([...updated.roles].sort());
        setPendingChange(null);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update this user."
        );
      }
    },
    [pendingChange, target]
  );

  const cancelChange = useCallback(() => {
    setPendingChange(null);
    setSubmitError(null);
  }, []);

  const backLink = (
    <Link
      href="/admin/users"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Users
    </Link>
  );

  if (!canView) {
    return <UserAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !target) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              {isNotFound ? "search_off" : "error"}
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">
              {isNotFound ? "User not found" : "Unable to load user"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This user account does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchUser}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  const fullName = `${target.first_name} ${target.last_name}`.trim();
  const isSuperTarget = targetIsSuperAdministrator(target);
  const permissionGroups = groupPermissionCodesByResource(target.permissions);
  const showSellerCreatePrompt = !target.seller_profile && canManageAdminSellers(actor);

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {userDisplayName(target)}
              </h1>
              <AdminStatusBadge
                status={null}
                label={target.is_active ? "Active" : "Inactive"}
                tone={target.is_active ? "success" : "neutral"}
              />
              {isSuperTarget && (
                <AdminStatusBadge status={null} label="Super Administrator" tone="accent" />
              )}
            </div>
            <p className="text-xs text-ink-muted mt-1">
              @{target.username}
              {target.email ? ` · ${target.email}` : ""}
            </p>
          </div>

          <div className="shrink-0 flex flex-col items-stretch sm:items-end gap-1.5">
            {deactivationLock ? (
              <p className="text-[11px] text-ink-faint max-w-xs sm:text-right">
                {deactivationLock}
              </p>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setSubmitError(null);
                  setPendingChange({ kind: "activation", nextActive: !target.is_active });
                }}
                className={`inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 ${
                  target.is_active
                    ? "bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600"
                    : "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary"
                }`}
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  {target.is_active ? "person_off" : "how_to_reg"}
                </span>
                {target.is_active ? "Deactivate account" : "Activate account"}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Basic information */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Basic Information
          </h2>
          <dl>
            <InfoRow label="User ID" value={`#${target.id}`} />
            <InfoRow label="Username" value={target.username} />
            <InfoRow label="Email" value={target.email || "—"} />
            <InfoRow label="First Name" value={target.first_name || "—"} />
            <InfoRow label="Last Name" value={target.last_name || "—"} />
            <InfoRow label="Full Name" value={fullName || "—"} />
            <InfoRow
              label="Account Status"
              value={target.is_active ? "Active" : "Inactive"}
            />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            Username, email and name are not editable here: the admin user endpoint accepts
            only <code className="font-mono">is_active</code> and{" "}
            <code className="font-mono">roles</code>. No password or credential field is
            exposed by the API at all.
          </p>
        </div>

        {/* Platform flags & linked profiles */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Platform Access
          </h2>
          <dl>
            <InfoRow
              label="Django Staff"
              value={
                <span className="flex items-center gap-2">
                  {target.is_staff ? "Yes" : "No"}
                  <span className="text-ink-faint text-[11px]">
                    (Django Admin access — separate from MiniShop RBAC)
                  </span>
                </span>
              }
            />
            <InfoRow label="Django Superuser" value={target.is_superuser ? "Yes" : "No"} />
            <InfoRow
              label="Full Platform Access"
              value={target.has_full_platform_access ? "Yes — wildcard (*)" : "No"}
            />
            <InfoRow label="Registered" value={formatDateTime(target.date_joined)} />
            <InfoRow label="Last Login" value={formatDateTime(target.last_login)} />
          </dl>

          <h3 className="text-xs font-extrabold text-ink uppercase tracking-wider mt-5 mb-2">
            Linked Profiles
          </h3>
          {!target.customer_profile && !target.seller_profile && !showSellerCreatePrompt ? (
            <p className="text-xs text-ink-muted">
              This account has no customer or seller profile.
            </p>
          ) : (
            <ul className="space-y-2 text-xs">
              {target.customer_profile && (
                <li className="rounded-xl border border-line p-3 bg-surface-alt/40">
                  <p className="font-bold text-ink mb-0.5">Customer Profile</p>
                  <p className="text-ink-muted">
                    {target.customer_profile.display_name || "No display name"}
                    {target.customer_profile.phone ? ` · ${target.customer_profile.phone}` : ""}
                  </p>
                  <Link
                    href={`/admin/customers/${target.customer_profile.id}`}
                    className="inline-flex items-center gap-1 mt-1 font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                  >
                    View customer profile
                    <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                      arrow_forward
                    </span>
                  </Link>
                </li>
              )}
              {target.seller_profile && (
                <li className="rounded-xl border border-line p-3 bg-surface-alt/40">
                  <p className="font-bold text-ink mb-0.5">Seller Profile</p>
                  <p className="text-ink-muted">
                    {target.seller_profile.business_name} ·{" "}
                    {humanizeToken(target.seller_profile.seller_type)} ·{" "}
                    {humanizeToken(target.seller_profile.status)}
                  </p>
                  <p className="text-[11px] text-ink-faint mt-0.5">
                    Seller type is a business attribute of the seller domain, not an RBAC role.
                  </p>
                  <Link
                    href={`/admin/sellers/${target.seller_profile.id}`}
                    className="inline-flex items-center gap-1 mt-1 font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                  >
                    View seller profile
                    <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                      arrow_forward
                    </span>
                  </Link>
                </li>
              )}
              {showSellerCreatePrompt && (
                <li className="rounded-xl border border-dashed border-line p-3">
                  <p className="font-bold text-ink mb-0.5">No Seller Profile</p>
                  <p className="text-ink-muted">
                    This account is not a registered seller yet.
                  </p>
                  <Link
                    href={`/admin/sellers/new?user_id=${target.id}`}
                    className="inline-flex items-center gap-1 mt-1 font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                  >
                    Create seller profile
                    <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                      arrow_forward
                    </span>
                  </Link>
                </li>
              )}
            </ul>
          )}
        </div>
      </div>

      {/* Role assignment */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-3">
          <div>
            <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
              Assigned Roles
            </h2>
            <p className="text-xs text-ink-muted mt-1 max-w-2xl">
              MiniShop permissions are granted through roles:{" "}
              <span className="font-mono text-[11px]">
                User → UserRole → Role → RolePermission → Permission
              </span>
              . Assigning a role is the only way this console changes what an account may do.
            </p>
          </div>
        </div>

        {target.roles.length === 0 ? (
          <p className="text-xs text-ink-muted mb-4">This user holds no MiniShop roles.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {target.roles.map((code) => (
              <AdminStatusBadge
                key={code}
                status={null}
                label={humanizeToken(code)}
                tone={isProtectedRoleCode(code) ? "accent" : "info"}
              />
            ))}
          </div>
        )}

        {roleEditingLock ? (
          <div className="rounded-xl border border-line bg-surface-alt/40 p-3 flex items-start gap-2">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[18px] text-ink-muted shrink-0"
            >
              lock
            </span>
            <p className="text-xs text-ink-muted">{roleEditingLock}</p>
          </div>
        ) : !canListRoles ? (
          <div className="rounded-xl border border-line bg-surface-alt/40 p-3 flex items-start gap-2">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[18px] text-ink-muted shrink-0"
            >
              info
            </span>
            <p className="text-xs text-ink-muted">
              Assigning roles also needs{" "}
              <code className="font-mono text-[11px]">roles.admin.view</code> so the console
              can list the roles available to assign.
            </p>
          </div>
        ) : rolesError ? (
          <p className="text-xs text-red-600">{rolesError}</p>
        ) : roles.length === 0 ? (
          <p className="text-xs text-ink-muted">Loading the role catalogue…</p>
        ) : (
          <>
            <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
              {roles.map((role) => {
                const lock = getRoleToggleLock(actor, target, role);
                const warning = lock ? null : getRoleToggleWarning(target, role);
                const checked = draftSet.has(role.code);
                const inputId = `role-${role.id}`;
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
                        disabled={Boolean(lock)}
                        onChange={() => toggleRole(role.code)}
                        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-primary)] disabled:cursor-not-allowed"
                        aria-describedby={lock || warning ? `${inputId}-lock` : undefined}
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
                          {!role.is_active && (
                            <AdminStatusBadge
                              status={null}
                              label="Inactive"
                              tone="neutral"
                              size="sm"
                            />
                          )}
                        </span>
                        <span className="block font-mono text-[10px] text-ink-muted">
                          {role.code}
                        </span>
                        {(lock || warning) && (
                          <span
                            id={`${inputId}-lock`}
                            className={`block text-[11px] mt-1 ${
                              warning ? "text-amber-600" : "text-ink-faint"
                            }`}
                          >
                            {lock ?? warning}
                          </span>
                        )}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>

            <div className="flex flex-col sm:flex-row sm:items-center gap-2 mt-4">
              <button
                type="button"
                disabled={!rolesDirty}
                onClick={() => {
                  setSubmitError(null);
                  setPendingChange({
                    kind: "roles",
                    desiredRoles: [...draftRoles].sort(),
                    added: roleDiff.added,
                    removed: roleDiff.removed,
                  });
                }}
                className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  save
                </span>
                Save role assignments
              </button>
              {rolesDirty && (
                <button
                  type="button"
                  onClick={resetRoleDraft}
                  className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  Discard changes
                </button>
              )}
              {rolesDirty && (
                <p className="text-[11px] text-ink-muted">
                  {roleDiff.added.length} to add · {roleDiff.removed.length} to remove
                </p>
              )}
            </div>
          </>
        )}
      </div>

      {/* Effective permissions */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-1">
          Effective Permissions
        </h2>
        <p className="text-xs text-ink-muted mb-4 max-w-2xl">
          Resolved by the backend (<span className="font-mono text-[11px]">
            rbac.services.get_user_permissions
          </span>
          ) — the same resolver every API authorization check uses. This console displays the
          result; it never recomputes it.
        </p>

        {target.has_full_platform_access ? (
          <div className="rounded-xl border border-accent/30 bg-accent/10 p-4 flex items-start gap-3">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[24px] text-accent shrink-0"
            >
              workspace_premium
            </span>
            <div>
              <p className="text-sm font-black text-ink">Full platform access</p>
              <p className="text-xs text-ink-muted mt-1 max-w-2xl">
                This account resolves to the wildcard permission{" "}
                <code className="font-mono text-[11px]">*</code> and is authorized for every
                MiniShop operation. It is not a list of individually assigned permissions, and
                the console does not present it as one.
              </p>
            </div>
          </div>
        ) : target.permissions.length === 0 ? (
          <p className="text-xs text-ink-muted">
            This account holds no MiniShop permissions.
          </p>
        ) : (
          <>
            <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint mb-3">
              {target.permissions.length} permission
              {target.permissions.length === 1 ? "" : "s"} across {permissionGroups.length}{" "}
              resource{permissionGroups.length === 1 ? "" : "s"}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {permissionGroups.map((group) => (
                <div
                  key={group.resource}
                  className="rounded-xl border border-line bg-surface-alt/40 p-3"
                >
                  <p className="text-[11px] font-extrabold uppercase tracking-wider text-ink mb-2">
                    {humanizeToken(group.resource)}
                  </p>
                  <ul className="space-y-1">
                    {group.codes.map((code) => (
                      <li key={code} className="font-mono text-[11px] text-ink-body break-all">
                        {code}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <AdminConfirmModal
        open={Boolean(pendingChange)}
        title={
          pendingChange?.kind === "activation"
            ? pendingChange.nextActive
              ? "Activate Account"
              : "Deactivate Account"
            : "Update Role Assignments"
        }
        message={
          <>
            {pendingChange?.kind === "activation" ? (
              pendingChange.nextActive ? (
                <>
                  Reactivate <strong>{target.username}</strong>? The account will be able to
                  sign in again with the roles it already holds.
                </>
              ) : (
                <>
                  Deactivate <strong>{target.username}</strong>? The account will no longer be
                  able to authenticate. Role assignments are kept, so reactivating restores
                  the same access.
                  {isSuperTarget && (
                    <span className="block mt-2">
                      This is a Super Administrator account. The backend refuses to deactivate
                      the last active one.
                    </span>
                  )}
                </>
              )
            ) : pendingChange?.kind === "roles" ? (
              <>
                Update role assignments for <strong>{target.username}</strong>?
                {pendingChange.added.length > 0 && (
                  <span className="block mt-2">
                    <strong>Granting:</strong> {pendingChange.added.join(", ")}
                  </span>
                )}
                {pendingChange.removed.length > 0 && (
                  <span className="block mt-1">
                    <strong>Revoking:</strong> {pendingChange.removed.join(", ")}
                  </span>
                )}
                <span className="block mt-2 text-ink-muted">
                  This changes the account&apos;s effective permissions immediately.
                </span>
              </>
            ) : null}
            {accountLock && <span className="block mt-2 text-red-600">{accountLock}</span>}
            {submitError && (
              <span className="block mt-2 font-semibold text-red-600">{submitError}</span>
            )}
          </>
        }
        confirmLabel={
          pendingChange?.kind === "activation"
            ? pendingChange.nextActive
              ? "Activate"
              : "Deactivate"
            : "Save assignments"
        }
        destructive={pendingChange?.kind === "activation" && !pendingChange.nextActive}
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this change is being made…"
        onConfirm={confirmChange}
        onCancel={cancelChange}
      />
    </div>
  );
}
