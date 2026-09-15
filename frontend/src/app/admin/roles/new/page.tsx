"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminPermissionCatalog,
  createAdminRole,
  getAdminPermissionCatalog,
} from "@/lib/admin-api";
import { AdminConfirmModal } from "@/components/admin/shared";
import {
  EMPTY_ROLE_FORM,
  RoleAccessNotice,
  RoleForm,
  type RoleFormValues,
  canManageAdminRoles,
  canViewAdminRoles,
} from "../roleGovernance";

export default function AdminRoleCreatePage() {
  const router = useRouter();
  const { user } = useAuth();

  const canView = canViewAdminRoles(user);
  const canManage = canManageAdminRoles(user);

  const [values, setValues] = useState<RoleFormValues>(EMPTY_ROLE_FORM);
  const [catalog, setCatalog] = useState<AdminPermissionCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const submit = useCallback(
    async (reason: string) => {
      const token = getAuthToken();
      if (!token) {
        setError("No active session token was found. Please sign in again.");
        return;
      }
      if (submitting) return;

      try {
        setSubmitting(true);
        setError(null);
        const created = await createAdminRole(token, {
          code: values.code.trim(),
          name: values.name.trim(),
          description: values.description.trim(),
          permissions: values.permissions,
          reason,
        });
        setConfirming(false);
        router.push(`/admin/roles/${created.id}`);
      } catch (err) {
        setError(err instanceof AdminApiError ? err.message : "Failed to create the role.");
      } finally {
        setSubmitting(false);
      }
    },
    [values, submitting, router]
  );

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

  if (!canManage) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              shield_lock
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">You are not authorized to create roles</p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              Creating a role requires{" "}
              <code className="font-mono text-[11px]">roles.admin.manage</code>. You can still
              inspect existing roles and their permissions.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {backLink}

      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">New role</h1>
        <p className="text-xs text-ink-muted max-w-3xl mt-1">
          A role bundles permissions so they can be granted to users as one job function. You
          may attach only the permissions you are authorized to delegate — the rest are shown
          locked, and the backend independently rejects any that slip through.
        </p>
      </div>

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        {catalogError ? (
          <p role="alert" className="text-xs font-semibold text-red-600">
            {catalogError}
          </p>
        ) : (
          <RoleForm
            mode="create"
            idPrefix="role-create"
            values={values}
            onChange={setValues}
            onSubmit={() => {
              setError(null);
              setConfirming(true);
            }}
            onCancel={() => router.push("/admin/roles")}
            submitting={submitting}
            submitLabel="Create role"
            error={error}
            catalog={catalog}
          />
        )}
      </div>

      <AdminConfirmModal
        open={confirming}
        title="Create Role"
        message={
          <>
            Create the role <strong>{values.name || values.code}</strong> (
            <code className="font-mono text-[11px]">{values.code}</code>) with{" "}
            <strong>{values.permissions.length}</strong> permission
            {values.permissions.length === 1 ? "" : "s"}?
            <span className="block mt-2 text-ink-muted">
              The role is created with no holders. Assign it to users from their account pages.
            </span>
            {error && <span className="block mt-2 font-semibold text-red-600">{error}</span>}
          </>
        }
        confirmLabel="Create role"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this role is being created…"
        loading={submitting}
        onConfirm={submit}
        onCancel={() => {
          setConfirming(false);
          setError(null);
        }}
      />
    </div>
  );
}
