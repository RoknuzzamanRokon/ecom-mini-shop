"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminShop, getAdminShops } from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  SHOP_STATUS_LABELS,
  SHOP_STATUS_OPTIONS,
  getAvailableShopActions,
  useShopStatusAction,
} from "./shopGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

export default function AdminShopsPage() {
  return (
    <Suspense fallback={<ShopsPageFallback />}>
      <AdminShopsPageContent />
    </Suspense>
  );
}

function ShopsPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminShopsPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const urlSearch = searchParams.get("search") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed into the URL (and
  // the actual filter) after a short debounce so we don't fire a request per
  // keystroke. Resynced from the URL during render (not an effect) whenever
  // it changes externally — e.g. browser back/forward or "Clear filters".
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

  const [shops, setShops] = useState<AdminShop[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchShops = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminShops(token, {
        search: urlSearch || undefined,
        status: urlStatus || undefined,
        page: urlPage,
      });
      setShops(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setShops([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load shops."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlPage]);

  useEffect(() => {
    fetchShops();
  }, [fetchShops]);

  const isFiltered = Boolean(urlSearch || urlStatus);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, status: null, page: null });
  }, [updateParams]);

  const handleActionSuccess = useCallback((updated: AdminShop) => {
    setShops((prev) => prev.map((shop) => (shop.id === updated.id ? updated : shop)));
  }, []);
  const { pendingAction, targetShop, submitError, requestAction, cancel, confirm } =
    useShopStatusAction(handleActionSuccess);

  const columns: AdminTableColumn<AdminShop>[] = useMemo(
    () => [
      {
        key: "shop",
        header: "Shop",
        render: (shop) => (
          <Link
            href={`/admin/shops/${shop.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{shop.name}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              /{shop.slug}
            </span>
          </Link>
        ),
        width: "w-56",
      },
      {
        key: "owner",
        header: "Owner",
        render: (shop) => (
          <span className="line-clamp-1">{shop.owner_business_name || "—"}</span>
        ),
      },
      {
        key: "status",
        header: "Status",
        render: (shop) => (
          <AdminStatusBadge status={shop.status} label={SHOP_STATUS_LABELS[shop.status]} />
        ),
      },
      {
        key: "phone",
        header: "Phone",
        render: (shop) => shop.phone || "—",
        hideOnMobile: true,
      },
      {
        key: "products",
        header: "Products",
        render: (shop) => shop.products_count,
        align: "right",
        hideOnMobile: true,
        width: "w-20",
      },
      {
        key: "created",
        header: "Created",
        render: (shop) => formatDate(shop.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminShop>[] = useMemo(
    () => [
      {
        key: "approve",
        label: "Approve",
        icon: "check_circle",
        tone: "primary",
        onClick: (shop) => {
          const descriptor = getAvailableShopActions(shop, user).find((a) => a.action === "approve");
          if (descriptor) requestAction(shop, descriptor);
        },
        isHidden: (shop) => !getAvailableShopActions(shop, user).some((a) => a.action === "approve"),
      },
      {
        key: "reject",
        label: "Reject",
        icon: "cancel",
        tone: "danger",
        onClick: (shop) => {
          const descriptor = getAvailableShopActions(shop, user).find((a) => a.action === "reject");
          if (descriptor) requestAction(shop, descriptor);
        },
        isHidden: (shop) => !getAvailableShopActions(shop, user).some((a) => a.action === "reject"),
      },
      {
        key: "suspend",
        label: "Suspend",
        icon: "block",
        tone: "danger",
        onClick: (shop) => {
          const descriptor = getAvailableShopActions(shop, user).find((a) => a.action === "suspend");
          if (descriptor) requestAction(shop, descriptor);
        },
        isHidden: (shop) => !getAvailableShopActions(shop, user).some((a) => a.action === "suspend"),
      },
      {
        key: "reactivate",
        label: "Reactivate",
        icon: "restart_alt",
        tone: "primary",
        onClick: (shop) => {
          const descriptor = getAvailableShopActions(shop, user).find(
            (a) => a.action === "reactivate"
          );
          if (descriptor) requestAction(shop, descriptor);
        },
        isHidden: (shop) =>
          !getAvailableShopActions(shop, user).some((a) => a.action === "reactivate"),
      },
    ],
    [user, requestAction]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Shops</h1>
          <p className="text-xs text-ink-muted">
            Review, approve, and govern multi-vendor storefronts across the platform.
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
              {totalCount.toLocaleString("en-US")} shop{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by name, slug, or owner…"
          value={searchInput}
          onChange={setSearchInput}
        />
        <AdminSelectField
          label="Status"
          value={urlStatus}
          options={SHOP_STATUS_OPTIONS}
          onChange={(value) => updateParams({ status: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminShop>
        caption="Platform shops"
        columns={columns}
        rows={shops}
        getRowId={(shop) => shop.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchShops}
        emptyTitle="No shops found"
        emptyMessage={
          isFiltered ? "No shops match the current filters." : "No shops have been registered yet."
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
        actions={actions}
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />

      <AdminConfirmModal
        open={Boolean(pendingAction && targetShop)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetShop && pendingAction ? pendingAction.confirmMessage(targetShop) : ""}
            {submitError && <p className="mt-2 font-semibold text-red-600">{submitError}</p>}
          </>
        }
        confirmLabel={pendingAction?.label ?? "Confirm"}
        destructive={pendingAction?.destructive ?? false}
        requireReason={pendingAction?.requiresReason ?? false}
        reasonRequired={pendingAction?.requiresReason ?? false}
        reasonLabel="Reason"
        reasonPlaceholder="Explain the decision for the seller's record…"
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
