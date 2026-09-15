"use client";

import React, { useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getManagementRoleLabel, isManagementUser } from "@/lib/admin-auth";
import {
  WILDCARD_PERMISSION,
  countConcretePermissions,
  formatRoleLabel,
  groupPermissions,
  hasFullPlatformAccess,
} from "./adminProfile";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-40 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value}</dd>
    </div>
  );
}

function SummaryTile({
  icon,
  value,
  label,
}: {
  icon: string;
  value: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-alt/40 px-3.5 py-3">
      <span
        aria-hidden="true"
        className="material-symbols-outlined text-[20px] text-ink-muted shrink-0"
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-base font-black text-ink leading-tight">{value}</p>
        <p className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">
          {label}
        </p>
      </div>
    </div>
  );
}

export default function AdminProfilePage() {
  const { user, isLoading } = useAuth();

  const roles = useMemo(() => user?.roles ?? [], [user]);
  const permissions = useMemo(() => user?.permissions ?? [], [user]);
  const groups = useMemo(() => groupPermissions(permissions), [permissions]);
  const fullAccess = hasFullPlatformAccess(user);
  const concreteCount = countConcretePermissions(permissions);

  const backLink = (
    <Link
      href="/admin"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Dashboard
    </Link>
  );

  // AdminGuard already blocks unauthenticated access and non-management users,
  // so this only covers the brief window while the session is being restored.
  if (isLoading || !user) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="flex items-center justify-center py-24" aria-busy="true">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      </div>
    );
  }

  const fullName = `${user.first_name} ${user.last_name}`.trim();
  const roleLabel = getManagementRoleLabel(user);
  const initial = (user.first_name?.[0] || user.username?.[0] || "A").toUpperCase();

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <div
              aria-hidden="true"
              className="w-14 h-14 shrink-0 rounded-2xl bg-primary/15 text-primary flex items-center justify-center font-black text-xl border border-primary/20"
            >
              {initial}
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {fullName || user.username}
              </h1>
              <p className="text-xs text-ink-muted mt-0.5">
                @{user.username}
                {user.email ? ` · ${user.email}` : ""}
              </p>
              <span className="inline-block mt-2 text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-md bg-primary/15 text-primary border border-primary/20">
                {roleLabel}
              </span>
            </div>
          </div>

          {/* This page never mutates the account; the backend exposes no
              self-service profile or permission endpoint to call anyway. */}
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint shrink-0">
            Read-only
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Account */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Account
          </h2>
          <dl>
            <InfoRow label="User ID" value={`#${user.id}`} />
            <InfoRow label="Username" value={user.username} />
            <InfoRow label="Email" value={user.email || "—"} />
            <InfoRow label="First Name" value={user.first_name || "—"} />
            <InfoRow label="Last Name" value={user.last_name || "—"} />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            These are the only account fields <code className="font-mono">/api/auth/me/</code>{" "}
            returns. It exposes no password, hash or token.
          </p>
        </div>

        {/* Management access */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Management Access
          </h2>
          <ul className="space-y-2 text-xs">
            <AccessLine
              granted={isManagementUser(user)}
              label="Management portal access"
              detail="Evaluated by isManagementUser() — the same check AdminGuard uses."
            />
            <AccessLine
              granted={user.is_staff}
              label="Django staff flag"
              detail="is_staff on the auth account."
            />
            <AccessLine
              granted={user.is_superuser}
              label="Superuser"
              detail="is_superuser bypasses every backend permission check."
            />
          </ul>
        </div>
      </div>

      {/* Roles */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
          My Roles
        </h2>
        {roles.length === 0 ? (
          <p className="text-xs text-ink-muted">
            No roles assigned.
            {user.is_superuser
              ? " This account is a Django superuser, which bypasses role checks entirely."
              : ""}
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {roles.map((role) => (
              <li
                key={role}
                className="rounded-xl border border-line bg-surface-alt/40 px-3 py-2"
              >
                <p className="text-xs font-bold text-ink">{formatRoleLabel(role)}</p>
                <p className="text-[10px] font-mono text-ink-muted">{role}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Permissions */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
          My Permissions
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
          <SummaryTile icon="badge" value={roles.length} label="Roles" />
          <SummaryTile icon="key" value={concreteCount} label="Permissions" />
          <SummaryTile icon="category" value={groups.length} label="Domains" />
        </div>

        {fullAccess && (
          <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3.5 py-3 mb-5">
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[20px] text-emerald-600 shrink-0"
            >
              verified_user
            </span>
            <div className="min-w-0">
              <p className="text-xs font-extrabold text-emerald-700">Full Platform Access</p>
              <p className="text-[11px] text-emerald-700/90 mt-0.5">
                This account holds the{" "}
                <code className="font-mono bg-emerald-500/15 px-1 rounded">
                  {WILDCARD_PERMISSION}
                </code>{" "}
                wildcard, so every backend permission check passes regardless of the individual
                grants listed below.
              </p>
            </div>
          </div>
        )}

        {concreteCount === 0 ? (
          <p className="text-xs text-ink-muted">
            {fullAccess
              ? "No individual permission codes are listed, but the wildcard above grants full access."
              : "No permissions assigned."}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {groups.map((group) => (
              <section
                key={group.key}
                aria-label={`${group.label} permissions`}
                className="rounded-xl border border-line p-3.5"
              >
                <h3 className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-2 flex items-center justify-between gap-2">
                  <span>{group.label}</span>
                  <span className="text-ink-faint font-bold">{group.codes.length}</span>
                </h3>
                <ul className="space-y-1">
                  {group.codes.map((code) => (
                    <li key={code} className="flex items-start gap-1.5 text-[11px]">
                      <span
                        aria-hidden="true"
                        className="material-symbols-outlined text-[14px] text-emerald-600 shrink-0 mt-px"
                      >
                        check
                      </span>
                      <code className="font-mono text-ink break-all">{code}</code>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}

        <p className="text-[11px] text-ink-faint mt-5">
          This list reflects what the backend reported for the current session. It is shown for
          reference only — the backend re-checks every request and remains the sole authority.
        </p>
      </div>
    </div>
  );
}

function AccessLine({
  granted,
  label,
  detail,
}: {
  granted: boolean;
  label: string;
  detail: string;
}) {
  return (
    <li className="flex items-start gap-2">
      <span
        aria-hidden="true"
        className={`material-symbols-outlined text-[16px] shrink-0 mt-px ${
          granted ? "text-emerald-600" : "text-ink-faint"
        }`}
      >
        {granted ? "check_circle" : "cancel"}
      </span>
      <span className="min-w-0">
        <span className={`font-bold ${granted ? "text-ink" : "text-ink-muted"}`}>
          {label}
        </span>
        <span className="sr-only">{granted ? " — granted" : " — not granted"}</span>
        <span className="block text-[10px] text-ink-muted">{detail}</span>
      </span>
    </li>
  );
}
