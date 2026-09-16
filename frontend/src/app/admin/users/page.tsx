"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminRole,
  AdminUserListItem,
  getAdminRoles,
  getAdminUsers,
} from "@/lib/admin-api";
import { formatDate, humanizeToken } from "@/lib/admin-format";
import { hasAnyPermission, isProtectedRoleCode } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatusBadge,
  type AdminSelectOption,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  UserAccessNotice,
  canManageAdminUsers,
  canViewAdminUsers,
  userDisplayName,
} from "./userGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

const STATUS_OPTIONS: AdminSelectOption[] = [
  { value: "true", label: "Active" },
  { value: "false", label: "Inactive" },
];

export default function AdminUsersPage() {
  return (
    <Suspense fallback={<UsersPageFallback />}>
      <AdminUsersPageContent />
    </Suspense>
  );
}

function UsersPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminUsersPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminUsers(user);
  const canManage = canManageAdminUsers(user);
  /**
   * The role filter is driven by GET /api/admin/roles/, which is gated by
   * 'roles.admin.view'. A user administrator without role-read access can still
   * use this page — they simply do not get the filter, rather than getting one
   * that always 403s.
   */
  const canListRoles = hasAnyPermission(user, ADMIN_PERMISSIONS.rolesView);

  const urlSearch = searchParams.get("search") ?? "";
  const urlStatus = searchParams.get("is_active") ?? "";
  const urlRole = searchParams.get("role") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed into the URL (and the
  // actual filter) after a short debounce. Resynced from the URL during render
  // whenever it changes externally — browser back/forward, or "Clear filters".
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
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const [users, setUsers] = useState<AdminUserListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const [roles, setRoles] = useState<AdminRole[]>([]);

  const fetchUsers = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminUsers(token, {
        search: urlSearch || undefined,
        is_active: urlStatus === "" ? undefined : urlStatus === "true",
        role: urlRole || undefined,
        page: urlPage,
      });
      setUsers(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setUsers([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load users."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlRole, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchUsers();
  }, [canView, fetchUsers]);

  /**
   * Roles populate the filter only. A failure here must never break the user
   * list, so it is swallowed: the filter simply does not appear.
   */
  useEffect(() => {
    if (!canView || !canListRoles) return;
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getAdminRoles(token)
      .then((data) => {
        if (!cancelled) setRoles(data);
      })
      .catch(() => {
        if (!cancelled) setRoles([]);
      });
    return () => {
      cancelled = true;
    };
  }, [canView, canListRoles]);

  const roleOptions: AdminSelectOption[] = useMemo(
    () => roles.map((role) => ({ value: role.code, label: role.name })),
    [roles]
  );

  const isFiltered = Boolean(urlSearch || urlStatus || urlRole);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, is_active: null, role: null, page: null });
  }, [updateParams]);

  const columns: AdminTableColumn<AdminUserListItem>[] = useMemo(
    () => [
      {
        key: "user",
        header: "User",
        render: (row) => (
          <Link
            href={`/admin/users/${row.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{userDisplayName(row)}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              @{row.username}
            </span>
          </Link>
        ),
        width: "w-56",
      },
      {
        key: "email",
        header: "Email",
        render: (row) => <span className="block line-clamp-1">{row.email || "—"}</span>,
        hideOnMobile: true,
      },
      {
        key: "roles",
        header: "Assigned Roles",
        render: (row) =>
          row.roles.length === 0 ? (
            <span className="text-ink-muted">No roles</span>
          ) : (
            <span className="flex flex-wrap gap-1">
              {row.roles.map((code) => (
                <AdminStatusBadge
                  key={code}
                  status={null}
                  label={humanizeToken(code)}
                  tone={isProtectedRoleCode(code) ? "accent" : "info"}
                  size="sm"
                />
              ))}
            </span>
          ),
      },
      {
        key: "status",
        header: "Account",
        render: (row) => (
          <AdminStatusBadge
            status={null}
            label={row.is_active ? "Active" : "Inactive"}
            tone={row.is_active ? "success" : "neutral"}
          />
        ),
      },
      {
        key: "joined",
        header: "Registered",
        render: (row) => formatDate(row.date_joined),
        hideOnMobile: true,
      },
      {
        key: "last_login",
        header: "Last Login",
        render: (row) => formatDate(row.last_login),
        hideOnMobile: true,
      },
    ],
    []
  );

  if (!canView) {
    return <UserAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Users</h1>
          <p className="text-xs text-ink-muted max-w-2xl">
            Platform accounts and their MiniShop role assignments. Open an account to review
            its effective permissions, assign roles, or change its active state.
          </p>
        </div>
        {canManage ? (
          <Link
            href="/admin/users/new"
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              add
            </span>
            New user
          </Link>
        ) : (
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint shrink-0">
            Read-only
          </p>
        )}
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} user{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by username, email, or name…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-80"
        />
        <AdminSelectField
          label="Account status"
          value={urlStatus}
          options={STATUS_OPTIONS}
          onChange={(value) => updateParams({ is_active: value || null, page: null })}
          placeholder="All"
        />
        {canListRoles && roleOptions.length > 0 && (
          <AdminSelectField
            label="Role"
            value={urlRole}
            options={roleOptions}
            onChange={(value) => updateParams({ role: value || null, page: null })}
            placeholder="All roles"
          />
        )}
      </AdminFilterBar>

      <AdminDataTable<AdminUserListItem>
        caption="Platform user accounts and their assigned MiniShop roles"
        columns={columns}
        rows={users}
        getRowId={(row) => row.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchUsers}
        emptyTitle="No users found"
        emptyMessage={
          isFiltered
            ? "No users match the current filters."
            : "No user accounts exist yet."
        }
        emptyAction={
          isFiltered ? (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Clear filters
            </button>
          ) : undefined
        }
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />
    </div>
  );
}
