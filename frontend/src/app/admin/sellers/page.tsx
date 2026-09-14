"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminSeller, getAdminSellers } from "@/lib/admin-api";
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
  SELLER_STATUS_LABELS,
  SELLER_STATUS_OPTIONS,
  SELLER_TYPE_LABELS,
  SELLER_TYPE_OPTIONS,
  SellerAccessNotice,
  canViewAdminSellers,
  getAvailableSellerActions,
  useSellerStatusAction,
} from "./sellerGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

export default function AdminSellersPage() {
  return (
    <Suspense fallback={<SellersPageFallback />}>
      <AdminSellersPageContent />
    </Suspense>
  );
}

function SellersPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminSellersPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminSellers(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  const urlSellerType = searchParams.get("seller_type") ?? "";
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

  const [sellers, setSellers] = useState<AdminSeller[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchSellers = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminSellers(token, {
        search: urlSearch || undefined,
        status: urlStatus || undefined,
        seller_type: urlSellerType || undefined,
        page: urlPage,
      });
      setSellers(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setSellers([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load sellers."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlSellerType, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchSellers();
  }, [canView, fetchSellers]);

  const isFiltered = Boolean(urlSearch || urlStatus || urlSellerType);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, status: null, seller_type: null, page: null });
  }, [updateParams]);

  const handleActionSuccess = useCallback((updated: AdminSeller) => {
    setSellers((prev) => prev.map((seller) => (seller.id === updated.id ? updated : seller)));
  }, []);
  const { pendingAction, targetSeller, submitError, requestAction, cancel, confirm } =
    useSellerStatusAction(handleActionSuccess);

  const columns: AdminTableColumn<AdminSeller>[] = useMemo(
    () => [
      {
        key: "seller",
        header: "Seller",
        render: (seller) => (
          <Link
            href={`/admin/sellers/${seller.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{seller.business_name}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              @{seller.username}
            </span>
          </Link>
        ),
        width: "w-56",
      },
      {
        key: "contact",
        header: "Contact",
        render: (seller) => (
          <span className="block line-clamp-1">{seller.business_email || seller.email || "—"}</span>
        ),
        hideOnMobile: true,
      },
      {
        key: "seller_type",
        header: "Type",
        render: (seller) => SELLER_TYPE_LABELS[seller.seller_type] ?? seller.seller_type,
        hideOnMobile: true,
      },
      {
        key: "status",
        header: "Status",
        render: (seller) => (
          <AdminStatusBadge status={seller.status} label={SELLER_STATUS_LABELS[seller.status]} />
        ),
      },
      {
        key: "shops",
        header: "Shops",
        render: (seller) => seller.shops_count,
        align: "right",
        hideOnMobile: true,
        width: "w-20",
      },
      {
        key: "created",
        header: "Applied",
        render: (seller) => formatDate(seller.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminSeller>[] = useMemo(
    () => [
      {
        key: "approve",
        label: "Approve",
        icon: "verified",
        tone: "primary",
        onClick: (seller) => {
          const descriptor = getAvailableSellerActions(seller, user).find(
            (a) => a.action === "approve"
          );
          if (descriptor) requestAction(seller, descriptor);
        },
        isHidden: (seller) =>
          !getAvailableSellerActions(seller, user).some((a) => a.action === "approve"),
      },
      {
        key: "reject",
        label: "Reject",
        icon: "cancel",
        tone: "danger",
        onClick: (seller) => {
          const descriptor = getAvailableSellerActions(seller, user).find(
            (a) => a.action === "reject"
          );
          if (descriptor) requestAction(seller, descriptor);
        },
        isHidden: (seller) =>
          !getAvailableSellerActions(seller, user).some((a) => a.action === "reject"),
      },
      {
        key: "suspend",
        label: "Suspend",
        icon: "block",
        tone: "danger",
        onClick: (seller) => {
          const descriptor = getAvailableSellerActions(seller, user).find(
            (a) => a.action === "suspend"
          );
          if (descriptor) requestAction(seller, descriptor);
        },
        isHidden: (seller) =>
          !getAvailableSellerActions(seller, user).some((a) => a.action === "suspend"),
      },
      {
        key: "reactivate",
        label: "Reactivate",
        icon: "restart_alt",
        tone: "primary",
        onClick: (seller) => {
          const descriptor = getAvailableSellerActions(seller, user).find(
            (a) => a.action === "reactivate"
          );
          if (descriptor) requestAction(seller, descriptor);
        },
        isHidden: (seller) =>
          !getAvailableSellerActions(seller, user).some((a) => a.action === "reactivate"),
      },
    ],
    [user, requestAction]
  );

  if (!canView) {
    return <SellerAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Sellers</h1>
          <p className="text-xs text-ink-muted">
            Review seller applications, verify business details, and govern the seller account
            lifecycle across the platform.
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
              {totalCount.toLocaleString("en-US")} seller{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by business, email, phone, or username…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-72"
        />
        <AdminSelectField
          label="Status"
          value={urlStatus}
          options={SELLER_STATUS_OPTIONS}
          onChange={(value) => updateParams({ status: value || null, page: null })}
        />
        <AdminSelectField
          label="Seller Type"
          value={urlSellerType}
          options={SELLER_TYPE_OPTIONS}
          onChange={(value) => updateParams({ seller_type: value || null, page: null })}
          className="sm:w-52"
        />
      </AdminFilterBar>

      <AdminDataTable<AdminSeller>
        caption="Platform sellers"
        columns={columns}
        rows={sellers}
        getRowId={(seller) => seller.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchSellers}
        emptyTitle="No sellers found"
        emptyMessage={
          isFiltered
            ? "No sellers match the current filters."
            : "No seller applications have been submitted yet."
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
        open={Boolean(pendingAction && targetSeller)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetSeller && pendingAction ? pendingAction.confirmMessage(targetSeller) : ""}
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
