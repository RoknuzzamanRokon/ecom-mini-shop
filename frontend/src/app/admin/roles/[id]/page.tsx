"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminPermissionCatalog,
  AdminRole,
  deleteAdminRole,
  getAdminPermissionCatalog,
  getAdminRoleDetail,
  updateAdminRole,
} from "@/lib/admin-api";
import { formatDateTime, humanizeToken } from "@/lib/admin-format";
import { SUPER_ADMINISTRATOR_CODE, hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import {
  RoleAccessNotice,
  RoleForm,
  type RoleFormValues,
  canManageAdminRoles,
  canViewAdminRoles,
  getPermissionEditLock,
  getRoleDeleteLock,
  getRoleEditLock,
  groupGrantedPermissions,
  roleToFormValues,
} from "../roleGovernance";

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
    <div className="space-y-6" aria-busy="true" aria-label="Loading role detail">
      <div className="h-6 w-40 bg-surface-alt animate-pulse rounded-md" />
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-4 w-32 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-3 w-full bg-surface-alt animate-pulse rounded-md" />
        <div className="h-3 w-3/4 bg-surface-alt animate-pulse rounded-md" />
      </div>
    </div>
  );
}

export default function AdminRoleDetailPage() {
  const params = useParams<{ id: string }>();
  const roleId = params.id;
  const router = useRouter();
  const { user } = useAuth();

  const canView = canViewAdminRoles(user);
  const canManage = canManageAdminRoles(user);
  /**
   * The "who holds this role" shortcut points at the user directory, which is
   * gated by 'users.admin.view'. Offering it to an operator who only holds
   * role permissions would lead straight to that module's access notice.
   */
  const canReachUserDirectory = hasAnyPermission(user, ADMIN_PERMISSIONS.usersView);

  const [role, setRole] = useState<AdminRole | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const [catalog, setCatalog] = useState<AdminPermissionCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<RoleFormValues | null>(null);
  const [confirmingSave, setConfirmingSave] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchRole = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminRoleDetail(token, roleId);
      setRole(data);
      setValues(roleToFormValues(data));
    } catch (err) {
      setRole(null);
      setError(err instanceof Error ? err : new Error("Failed to load role."));
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  useEffect(() => {
    if (!canView) return;
    fetchRole();
  }, [canView, fetchRole]);

  useEffect(() => {
    if (!canView) return;
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getAdminPermissionCatalog(token)
      .then((data) => {
        if (!cancelled) {
          setCatalog(data);
          setCatalogError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCatalog(null);
          setCatalogError(
            err instanceof AdminApiError
              ? err.message
              : "Failed to load the permission catalogue."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canView]);

  const editLock = role ? getRoleEditLock(user, role) : null;
  const deleteLock = role ? getRoleDeleteLock(user, role) : null;
  const permissionLock = role ? getPermissionEditLock(user, role, catalog) : null;
  /**
   * Without the catalogue the selector cannot render, and the delegation flags
   * that make it safe are unknown — so permission editing is withheld and said
   * so, rather than leaving the form on "Loading…" indefinitely. Name,
   * description and active state remain editable.
   */
  const effectivePermissionLock =
    permissionLock ??
    (catalogError
      ? `The permission catalogue could not be loaded (${catalogError}), so the permission set cannot be edited right now. Other role fields can still be saved.`
      : null);

  const grantedGroups = useMemo(
    () => (role ? groupGrantedPermissions(role.permissions, catalog) : []),
    [role, catalog]
  );

  /**
   * `permissions` is sent ONLY when the operator actually changed the set. The
   * backend replaces every RolePermission row whenever the key is present, so
   * omitting an unchanged set keeps an unrelated edit (a rename, say) from
   * rewriting the role's grants.
   */
  const permissionsChanged = useMemo(() => {
    if (!role || !values) return false;
    const before = [...role.permissions].sort().join("|");
    const after = [...values.permissions].sort().join("|");
    return before !== after;
  }, [role, values]);

  const permissionDiff = useMemo(() => {
    if (!role || !values) return { added: [] as string[], removed: [] as string[] };
    const before = new Set(role.permissions);
    const after = new Set(values.permissions);
    return {
      added: values.permissions.filter((code) => !before.has(code)).sort(),
      removed: role.permissions.filter((code) => !after.has(code)).sort(),
    };
  }, [role, values]);

  const save = useCallback(
    async (reason: string) => {
      if (!role || !values) return;
      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }
      if (submitting) return;

      try {
        setSubmitting(true);
        setSubmitError(null);
        const updated = await updateAdminRole(token, role.id, {
          name: values.name.trim(),
          description: values.description.trim(),
          is_active: values.is_active,
          ...(permissionsChanged ? { permissions: values.permissions } : {}),
          reason,
        });
        // The response is authoritative — never assume the change we asked for.
        setRole(updated);
        setValues(roleToFormValues(updated));
        setConfirmingSave(false);
        setEditing(false);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update the role."
        );
      } finally {
        setSubmitting(false);
      }
    },
    [role, values, permissionsChanged, submitting]
  );

  const remove = useCallback(async () => {
    if (!role) return;
    const token = getAuthToken();
    if (!token) {
      setSubmitError("No active session token was found. Please sign in again.");
      return;
    }
    if (submitting) return;

    try {
      setSubmitting(true);
      setSubmitError(null);
      await deleteAdminRole(token, role.id);
      setConfirmingDelete(false);
      router.push("/admin/roles");
    } catch (err) {
      setSubmitError(
        err instanceof AdminApiError ? err.message : "Failed to delete the role."
      );
    } finally {
      setSubmitting(false);
    }
  }, [role, submitting, router]);

  const backLink = (
    <Link
      href="/admin/roles"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Roles
    </Link>
  );

  if (!canView) {
    return <RoleAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !role || !values) {
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
              {isNotFound ? "Role not found" : "Unable to load role"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This role does not exist or may have been deleted."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchRole}
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

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {role.name}
              </h1>
              <AdminStatusBadge
                status={null}
                label={role.is_active ? "Active" : "Inactive"}
                tone={role.is_active ? "success" : "neutral"}
              />
              {role.is_protected && (
                <AdminStatusBadge status={null} label="Protected" tone="accent" />
              )}
            </div>
            <p className="font-mono text-xs text-ink-muted mt-1">{role.code}</p>
            {role.description && (
              <p className="text-xs text-ink-body mt-2 max-w-2xl">{role.description}</p>
            )}
            <p className="text-[11px] text-ink-muted mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="flex items-center gap-1.5">
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  key
                </span>
                {role.permissions.length} permission
                {role.permissions.length === 1 ? "" : "s"}
              </span>
              <span className="flex items-center gap-1.5">
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  group
                </span>
                {role.user_count} active holder{role.user_count === 1 ? "" : "s"}
              </span>
            </p>
          </div>

          {canManage && !editing && (
            <div className="shrink-0 flex flex-col items-stretch sm:items-end gap-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={Boolean(editLock)}
                  onClick={() => {
                    setValues(roleToFormValues(role));
                    setSubmitError(null);
                    setEditing(true);
                  }}
                  className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    edit
                  </span>
                  Edit role
                </button>
                <button
                  type="button"
                  disabled={Boolean(deleteLock)}
                  onClick={() => {
                    setSubmitError(null);
                    setConfirmingDelete(true);
                  }}
                  className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg border border-red-600/40 text-red-600 hover:bg-red-500/10 text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    delete
                  </span>
                  Delete
                </button>
              </div>
              {(editLock || deleteLock) && (
                <p className="text-[11px] text-ink-faint max-w-xs sm:text-right">
                  {editLock ?? deleteLock}
                </p>
              )}
            </div>
          )}
        </div>

        {role.code === SUPER_ADMINISTRATOR_CODE && (
          <div className="mt-4 rounded-xl border border-accent/30 bg-accent/10 p-3 flex items-start gap-2.5">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[20px] text-accent shrink-0"
            >
              workspace_premium
            </span>
            <p className="text-xs text-ink-muted">
              <strong className="text-ink">Full platform access.</strong> Holders of this role
              resolve to the wildcard permission{" "}
              <code className="font-mono text-[11px]">*</code> in{" "}
              <span className="font-mono text-[11px]">rbac.services.get_user_permissions</span>
              , which authorizes every MiniShop operation regardless of the grants listed
              below.
            </p>
          </div>
        )}
      </div>

      {editing ? (
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-4">
            Edit role
          </h2>
          <RoleForm
            mode="edit"
            idPrefix={`role-edit-${role.id}`}
            values={values}
            onChange={setValues}
            onSubmit={() => {
              setSubmitError(null);
              setConfirmingSave(true);
            }}
            onCancel={() => {
              setValues(roleToFormValues(role));
              setSubmitError(null);
              setEditing(false);
            }}
            submitting={submitting}
            submitLabel="Save changes"
            error={submitError}
            catalog={catalog}
            permissionLock={effectivePermissionLock}
          />
        </div>
      ) : (
        <>
          {/* Granted permissions */}
          <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
            <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-1">
              Granted Permissions
            </h2>
            <p className="text-xs text-ink-muted mb-4 max-w-2xl">
              Every user holding this role receives these permissions through{" "}
              <span className="font-mono text-[11px]">RolePermission</span>.
            </p>

            {effectivePermissionLock && !role.is_protected && (
              <div className="mb-4 rounded-xl border border-line bg-surface-alt/40 p-3 flex items-start gap-2">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-ink-muted shrink-0"
                >
                  lock
                </span>
                <p className="text-xs text-ink-muted">{effectivePermissionLock}</p>
              </div>
            )}

            {role.permissions.length === 0 ? (
              <p className="text-xs text-ink-muted">
                This role grants no permissions. Holders receive nothing from it.
              </p>
            ) : (
              <>
                <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint mb-3">
                  {role.permissions.length} permission
                  {role.permissions.length === 1 ? "" : "s"} across {grantedGroups.length}{" "}
                  resource{grantedGroups.length === 1 ? "" : "s"}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {grantedGroups.map((group) => (
                    <div
                      key={group.resource}
                      className="rounded-xl border border-line bg-surface-alt/40 p-3"
                    >
                      <p className="text-[11px] font-extrabold uppercase tracking-wider text-ink mb-2">
                        {humanizeToken(group.resource)}
                      </p>
                      <ul className="space-y-1.5">
                        {group.permissions.map((permission) => (
                          <li key={permission.code}>
                            <span className="block font-mono text-[11px] text-ink-body break-all">
                              {permission.code}
                            </span>
                            {permission.name && (
                              <span className="block text-[10px] text-ink-faint">
                                {permission.name}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Metadata */}
          <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
            <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
              Role Metadata
            </h2>
            <dl>
              <InfoRow label="Role ID" value={`#${role.id}`} />
              <InfoRow label="Code" value={<span className="font-mono">{role.code}</span>} />
              <InfoRow label="Status" value={role.is_active ? "Active" : "Inactive"} />
              <InfoRow
                label="Protected"
                value={
                  role.is_protected
                    ? "Yes — cannot be modified or deleted by any account"
                    : "No"
                }
              />
              <InfoRow label="Active Holders" value={role.user_count} />
              <InfoRow label="Created" value={formatDateTime(role.created_at)} />
              <InfoRow label="Updated" value={formatDateTime(role.updated_at)} />
            </dl>
            {role.user_count > 0 && canReachUserDirectory && (
              <p className="text-[11px] text-ink-faint mt-3">
                To see who holds this role, filter the{" "}
                <Link
                  href={`/admin/users?role=${encodeURIComponent(role.code)}`}
                  className="font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
                >
                  user directory
                </Link>{" "}
                by this role.
              </p>
            )}
          </div>
        </>
      )}

      <AdminConfirmModal
        open={confirmingSave}
        title="Save Role Changes"
        message={
          <>
            Save changes to <strong>{role.name}</strong> (
            <code className="font-mono text-[11px]">{role.code}</code>)?
            {permissionsChanged ? (
              <>
                {permissionDiff.added.length > 0 && (
                  <span className="block mt-2">
                    <strong>Granting:</strong> {permissionDiff.added.join(", ")}
                  </span>
                )}
                {permissionDiff.removed.length > 0 && (
                  <span className="block mt-1">
                    <strong>Revoking:</strong> {permissionDiff.removed.join(", ")}
                  </span>
                )}
                <span className="block mt-2 text-ink-muted">
                  This immediately changes the effective permissions of all {role.user_count}{" "}
                  account{role.user_count === 1 ? "" : "s"} holding this role.
                </span>
              </>
            ) : (
              <span className="block mt-2 text-ink-muted">
                The permission set is unchanged and will not be resubmitted.
              </span>
            )}
            {submitError && (
              <span className="block mt-2 font-semibold text-red-600">{submitError}</span>
            )}
          </>
        }
        confirmLabel="Save changes"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this role is being changed…"
        loading={submitting}
        onConfirm={save}
        onCancel={() => {
          setConfirmingSave(false);
          setSubmitError(null);
        }}
      />

      <AdminConfirmModal
        open={confirmingDelete}
        title="Delete Role"
        message={
          <>
            Permanently delete <strong>{role.name}</strong> (
            <code className="font-mono text-[11px]">{role.code}</code>)? This cannot be undone.
            <span className="block mt-2 text-ink-muted">
              Deactivating the role instead keeps its definition and history, and is
              reversible.
            </span>
            {submitError && (
              <span className="block mt-2 font-semibold text-red-600">{submitError}</span>
            )}
          </>
        }
        confirmLabel="Delete role"
        destructive
        loading={submitting}
        onConfirm={remove}
        onCancel={() => {
          setConfirmingDelete(false);
          setSubmitError(null);
        }}
      />
    </div>
  );
}
