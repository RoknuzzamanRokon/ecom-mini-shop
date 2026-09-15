"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminRole, getAdminRoles } from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import {
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminStatCard,
  AdminStatusBadge,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  RoleAccessNotice,
  canManageAdminRoles,
  canViewAdminRoles,
} from "./roleGovernance";

/**
 * Client-side page size.
 *
 * GET /api/admin/roles/ applies no paginator and reads no filter parameters —
 * it always returns EVERY role. Searching and paging the complete set locally
 * is therefore accurate: unlike the other admin modules, there is no risk of
 * presenting one server page as though it were the whole result.
 */
const PAGE_SIZE = 20;

export default function AdminRolesPage() {
  return (
    <Suspense fallback={<RolesPageFallback />}>
      <AdminRolesPageContent />
    </Suspense>
  );
}

function RolesPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminRolesPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminRoles(user);
  const canManage = canManageAdminRoles(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [syncedUrlSearch, setSyncedUrlSearch] = useState(urlSearch);
  if (urlSearch !== syncedUrlSearch) {
    setSyncedUrlSearch(urlSearch);
    setSearchInput(urlSearch);
  }

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([key, value]) => {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      });
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [searchParams, router, pathname]
  );

  useEffect(() => {
    const handle = setTimeout(() => {
      if (searchInput !== urlSearch) {
        updateParams({ search: searchInput || null, page: null });
      }
    }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchRoles = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setRoles(await getAdminRoles(token));
    } catch (err) {
      setRoles([]);
      setError(err instanceof Error ? err : new Error("Failed to load roles."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canView) return;
    fetchRoles();
  }, [canView, fetchRoles]);

  const filteredRoles = useMemo(() => {
    const needle = urlSearch.trim().toLowerCase();
    if (!needle) return roles;
    return roles.filter(
      (role) =>
        role.name.toLowerCase().includes(needle) ||
        role.code.toLowerCase().includes(needle) ||
        role.description.toLowerCase().includes(needle)
    );
  }, [roles, urlSearch]);

  const pagedRoles = useMemo(
    () => filteredRoles.slice((urlPage - 1) * PAGE_SIZE, urlPage * PAGE_SIZE),
    [filteredRoles, urlPage]
  );

  const stats = useMemo(() => {
    const protectedCount = roles.filter((role) => role.is_protected).length;
    return {
      total: roles.length,
      // Everything that is not a protected system role — i.e. what this module
      // can actually create, edit and delete.
      custom: roles.length - protectedCount,
      protected: protectedCount,
      inactive: roles.filter((role) => !role.is_active).length,
    };
  }, [roles]);

  const isFiltered = Boolean(urlSearch);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, page: null });
  }, [updateParams]);

  const columns: AdminTableColumn<AdminRole>[] = useMemo(
    () => [
      {
        key: "role",
        header: "Role",
        render: (role) => (
          <Link
            href={`/admin/roles/${role.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{role.name}</span>
            <span className="block font-mono text-[11px] font-medium text-ink-muted line-clamp-1">
              {role.code}
            </span>
          </Link>
        ),
        width: "w-56",
      },
      {
        key: "description",
        header: "Description",
        render: (role) => (
          <span className="block line-clamp-2 text-ink-muted">{role.description || "—"}</span>
        ),
        hideOnMobile: true,
      },
      {
        key: "permissions",
        header: "Permissions",
        render: (role) => (
          <span className="font-bold text-ink">{role.permissions.length}</span>
        ),
        align: "right",
        width: "w-28",
      },
      {
        key: "users",
        header: "Holders",
        render: (role) => role.user_count,
        align: "right",
        hideOnMobile: true,
        width: "w-24",
      },
      {
        key: "status",
        header: "Status",
        render: (role) => (
          <span className="flex flex-wrap items-center gap-1">
            <AdminStatusBadge
              status={null}
              label={role.is_active ? "Active" : "Inactive"}
              tone={role.is_active ? "success" : "neutral"}
              size="sm"
            />
            {role.is_protected && (
              <AdminStatusBadge status={null} label="Protected" tone="accent" size="sm" />
            )}
          </span>
        ),
      },
      {
        key: "created",
        header: "Created",
        render: (role) => formatDate(role.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  if (!canView) {
    return <RoleAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Roles &amp; Permissions
          </h1>
          <p className="text-xs text-ink-muted max-w-2xl">
            MiniShop RBAC role definitions and the permissions each one grants. Permissions
            reach users only through roles:{" "}
            <span className="font-mono text-[11px]">
              Role → RolePermission → Permission
            </span>
            .
          </p>
        </div>
        {canManage && (
          <Link
            href="/admin/roles/new"
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              add
            </span>
            New role
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <AdminStatCard
          title="Total roles"
          value={stats.total}
          icon="shield_person"
          tone="primary"
          loading={loading}
          description="Every role defined in the RBAC system."
        />
        <AdminStatCard
          title="Editable roles"
          value={stats.custom}
          icon="tune"
          tone="info"
          loading={loading}
          description={`${stats.inactive} inactive`}
        />
        <AdminStatCard
          title="Protected roles"
          value={stats.protected}
          icon="lock"
          tone="accent"
          loading={loading}
          description="Cannot be modified or deleted by any account."
        />
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {filteredRoles.length.toLocaleString("en-US")} role
              {filteredRoles.length === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by name, code, or description…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-80"
        />
      </AdminFilterBar>

      <AdminDataTable<AdminRole>
        caption="MiniShop RBAC roles and their permission grant counts"
        columns={columns}
        rows={pagedRoles}
        getRowId={(role) => role.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchRoles}
        emptyTitle="No roles found"
        emptyMessage={
          isFiltered ? "No roles match the current search." : "No roles are defined yet."
        }
        emptyAction={
          isFiltered ? (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Clear search
            </button>
          ) : undefined
        }
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={filteredRoles.length}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />
    </div>
  );
}
