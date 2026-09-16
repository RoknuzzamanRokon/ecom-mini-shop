"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminRole, createAdminUser, getAdminRoles } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { AdminConfirmModal } from "@/components/admin/shared";
import {
  EMPTY_USER_CREATE_FORM,
  UserAccessNotice,
  UserCreateForm,
  canManageAdminUsers,
  canViewAdminUsers,
  summarizeRoleCodes,
  type UserCreateFormValues,
} from "../userGovernance";

export default function AdminUserCreatePage() {
  const router = useRouter();
  const { user: actor } = useAuth();

  const canView = canViewAdminUsers(actor);
  const canManage = canManageAdminUsers(actor);
  const canListRoles = hasAnyPermission(actor, ADMIN_PERMISSIONS.rolesView);

  const [values, setValues] = useState<UserCreateFormValues>(EMPTY_USER_CREATE_FORM);
  const [roles, setRoles] = useState<AdminRole[] | null>(null);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canView || !canManage || !canListRoles) return;
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
  }, [canView, canManage, canListRoles]);

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
        const created = await createAdminUser(token, {
          username: values.username.trim(),
          email: values.email.trim(),
          password: values.password,
          password_confirm: values.password_confirm,
          first_name: values.first_name.trim(),
          last_name: values.last_name.trim(),
          is_active: values.is_active,
          roles: values.roles,
          reason,
        });
        setConfirming(false);
        router.push(`/admin/users/${created.id}`);
      } catch (err) {
        setError(err instanceof AdminApiError ? err.message : "Failed to create the user.");
      } finally {
        setSubmitting(false);
      }
    },
    [values, submitting, router]
  );

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
            <p className="text-sm font-bold text-ink">You are not authorized to create users</p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              Creating a user account requires{" "}
              <code className="font-mono text-[11px]">users.admin.manage</code>. You can still
              browse the existing user directory.
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
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">New user</h1>
        <p className="text-xs text-ink-muted max-w-3xl mt-1">
          Creates a MiniShop platform account. Role assignment follows the same delegation
          boundary as editing an existing account — a protected role (
          <code className="font-mono text-[11px]">SUPER_ADMINISTRATOR</code>,{" "}
          <code className="font-mono text-[11px]">ADMINISTRATOR</code>) can only be granted by a
          Super Administrator, and is shown locked otherwise. This does not create a customer or
          seller profile — those are separate steps.
        </p>
      </div>

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <UserCreateForm
          idPrefix="user-create"
          values={values}
          onChange={setValues}
          onSubmit={() => {
            setError(null);
            setConfirming(true);
          }}
          onCancel={() => router.push("/admin/users")}
          submitting={submitting}
          error={error}
          actor={actor}
          roles={roles}
          rolesError={rolesError}
          canListRoles={canListRoles}
        />
      </div>

      <AdminConfirmModal
        open={confirming}
        title="Create User"
        message={
          <>
            Create the account <strong>{values.username || "(unnamed)"}</strong> (
            {values.email}) with <strong>{summarizeRoleCodes(values.roles)}</strong>?
            <span className="block mt-2 text-ink-muted">
              {values.is_active
                ? "The account will be able to sign in immediately."
                : "The account is created inactive and cannot sign in until activated."}
            </span>
            {error && <span className="block mt-2 font-semibold text-red-600">{error}</span>}
          </>
        }
        confirmLabel="Create user"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this account is being created…"
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
