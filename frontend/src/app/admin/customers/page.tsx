"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminCustomerListItem, getAdminCustomers } from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import {
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminStatusBadge,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  CustomerAccessNotice,
  canViewAdminCustomers,
  customerDisplayName,
} from "./customerDirectory";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

export default function AdminCustomersPage() {
  return (
    <Suspense fallback={<CustomersPageFallback />}>
      <AdminCustomersPageContent />
    </Suspense>
  );
}

function CustomersPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminCustomersPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminCustomers(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed into the URL (and the
  // actual filter) after a short debounce so we don't fire a request per
  // keystroke. Resynced from the URL during render (not an effect) whenever it
  // changes externally — e.g. browser back/forward or "Clear filters".
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

  const [customers, setCustomers] = useState<AdminCustomerListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchCustomers = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminCustomers(token, {
        search: urlSearch || undefined,
        page: urlPage,
      });
      setCustomers(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setCustomers([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load customers."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchCustomers();
  }, [canView, fetchCustomers]);

  const isFiltered = Boolean(urlSearch);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, page: null });
  }, [updateParams]);

  const columns: AdminTableColumn<AdminCustomerListItem>[] = useMemo(
    () => [
      {
        key: "customer",
        header: "Customer",
        render: (customer) => (
          <Link
            href={`/admin/customers/${customer.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{customerDisplayName(customer)}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              @{customer.username}
            </span>
          </Link>
        ),
        width: "w-60",
      },
      {
        key: "email",
        header: "Email",
        render: (customer) => (
          <span className="block line-clamp-1">{customer.email || "—"}</span>
        ),
        hideOnMobile: true,
      },
      {
        key: "phone",
        header: "Phone",
        render: (customer) => customer.phone || "—",
        hideOnMobile: true,
      },
      {
        key: "orders",
        header: "Orders",
        render: (customer) => customer.orders_count,
        align: "right",
        hideOnMobile: true,
        width: "w-20",
      },
      {
        key: "status",
        header: "Account",
        render: (customer) => (
          <AdminStatusBadge
            status={null}
            label={customer.is_active ? "Active" : "Inactive"}
            tone={customer.is_active ? "success" : "neutral"}
          />
        ),
      },
      {
        key: "joined",
        header: "Registered",
        render: (customer) => formatDate(customer.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  if (!canView) {
    return <CustomerAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Customers</h1>
          <p className="text-xs text-ink-muted">
            Read-only directory of customer profiles for support and inspection. This module makes
            no changes to customer accounts.
          </p>
        </div>
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} customer{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by username, email, name, or phone…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-96"
        />
      </AdminFilterBar>

      <AdminDataTable<AdminCustomerListItem>
        caption="Customer profile directory"
        columns={columns}
        rows={customers}
        getRowId={(customer) => customer.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchCustomers}
        emptyTitle="No customers found"
        emptyMessage={
          isFiltered
            ? "No customers match the current search."
            : "No customer profiles have been created yet."
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
        totalCount={totalCount}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />
    </div>
  );
}
