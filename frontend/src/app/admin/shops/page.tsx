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
  canCreateAdminShops,
  getAvailableShopActions,
  useShopStatusAction,
} from "./shopGovernance";
import { useLatestRequest } from "@/hooks/useLatestRequest";

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
  // One seller's shops, by SellerProfile id: where "View this seller's shops"
  // on the seller page leads (BUG-081).
  const ownerParam = Number(searchParams.get("owner"));
  const urlOwner = Number.isInteger(ownerParam) && ownerParam > 0 ? ownerParam : null;

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
    // Full dependencies: the timer must commit through the current
    // updateParams, or it rewrites the URL from an old snapshot and drops a
    // filter changed meanwhile (BUG-074).
  }, [searchInput, urlSearch, updateParams]);

  const [shops, setShops] = useState<AdminShop[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  // Only the newest request may set the list (BUG-073).
  const beginRequest = useLatestRequest();

  const fetchShops = useCallback(async () => {
    const isLatest = beginRequest();
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
        owner: urlOwner ?? undefined,
        page: urlPage,
      });
      if (!isLatest()) return;
      setShops(data.results);
      setTotalCount(data.count);
    } catch (err) {
      if (!isLatest()) return;
      setShops([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load shops."));
    } finally {
      if (isLatest()) setLoading(false);
    }
  }, [urlSearch, urlStatus, urlOwner, urlPage, beginRequest]);

  useEffect(() => {
    fetchShops();
  }, [fetchShops]);

  const isFiltered = Boolean(urlSearch || urlStatus || urlOwner);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, status: null, owner: null, page: null });
  }, [updateParams]);
  // Every row is the owner's, so any row can name them.
  const ownerName = shops.find((shop) => shop.owner_id === urlOwner)?.owner_business_name;

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

  const canCreate = canCreateAdminShops(user);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Shops</h1>
          <p className="text-xs text-ink-muted">
            Review, approve, and govern multi-vendor storefronts across the platform.
          </p>
        </div>
        {canCreate && (
          <Link
            href="/admin/shops/new"
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              add
            </span>
            Create shop
          </Link>
        )}
      </div>

      {urlOwner && (
        <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>Showing the shops owned by</span>
          <Link
            href={`/admin/sellers/${urlOwner}`}
            className="font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            {ownerName ?? `seller #${urlOwner}`}
          </Link>
          <button
            type="button"
            onClick={() => updateParams({ owner: null, page: null })}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border border-line hover:bg-surface-alt font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
              close
            </span>
            Show all owners
          </button>
        </p>
      )}

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
