"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminOrderListItem, getAdminOrders } from "@/lib/admin-api";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminDateField,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  ORDER_STATUS_LABELS,
  ORDER_STATUS_OPTIONS,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_OPTIONS,
  OrderAccessNotice,
  canViewAdminOrders,
  getAvailableOrderActions,
  useOrderStatusAction,
} from "./orderGovernance";

/** Matches StandardResultsSetPagination.page_size in shop/api_views.py (the backend's default). */
const PAGE_SIZE = 12;

export default function AdminOrdersPage() {
  return (
    <Suspense fallback={<OrdersPageFallback />}>
      <AdminOrdersPageContent />
    </Suspense>
  );
}

function OrdersPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminOrdersPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminOrders(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  const urlPaymentStatus = searchParams.get("payment_status") ?? "";
  const urlStartDate = searchParams.get("start_date") ?? "";
  const urlEndDate = searchParams.get("end_date") ?? "";
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

  const [orders, setOrders] = useState<AdminOrderListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchOrders = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminOrders(token, {
        search: urlSearch || undefined,
        status: urlStatus || undefined,
        payment_status: urlPaymentStatus || undefined,
        start_date: urlStartDate || undefined,
        end_date: urlEndDate || undefined,
        page: urlPage,
      });
      setOrders(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setOrders([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load orders."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlPaymentStatus, urlStartDate, urlEndDate, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchOrders();
  }, [canView, fetchOrders]);

  const isFiltered = Boolean(urlSearch || urlStatus || urlPaymentStatus || urlStartDate || urlEndDate);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({
      search: null,
      status: null,
      payment_status: null,
      start_date: null,
      end_date: null,
      page: null,
    });
  }, [updateParams]);

  const handleActionSuccess = useCallback((updated: { id: number; status: string }) => {
    setOrders((prev) =>
      prev.map((order) => (order.id === updated.id ? { ...order, status: updated.status } : order))
    );
  }, []);
  const { pendingAction, targetOrder, submitError, requestAction, cancel, confirm } =
    useOrderStatusAction<AdminOrderListItem>(handleActionSuccess);

  const columns: AdminTableColumn<AdminOrderListItem>[] = useMemo(
    () => [
      {
        key: "order",
        header: "Order",
        render: (order) => (
          <Link
            href={`/admin/orders/${order.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1 font-mono">{order.order_number}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              {order.total_items_count} item{order.total_items_count === 1 ? "" : "s"}
            </span>
          </Link>
        ),
        width: "w-52",
      },
      {
        key: "customer",
        header: "Customer",
        render: (order) => (
          <div className="min-w-0">
            <span className="block line-clamp-1 font-semibold text-ink">
              {order.customer.name || "—"}
            </span>
            <span className="block text-[11px] text-ink-muted line-clamp-1">
              {order.customer.phone || order.customer.email || "—"}
            </span>
          </div>
        ),
      },
      {
        key: "total",
        header: "Total",
        render: (order) => <span className="font-bold text-ink">{formatTaka(order.total_amount)}</span>,
        align: "right",
        width: "w-28",
      },
      {
        key: "status",
        header: "Status",
        render: (order) => (
          <AdminStatusBadge status={order.status} label={ORDER_STATUS_LABELS[order.status]} />
        ),
      },
      {
        key: "payment",
        header: "Payment",
        render: (order) =>
          order.payment_status ? (
            <AdminStatusBadge
              status={order.payment_status}
              label={PAYMENT_STATUS_LABELS[order.payment_status]}
              size="sm"
            />
          ) : (
            <span className="text-[11px] text-ink-faint">No payment</span>
          ),
        hideOnMobile: true,
      },
      {
        key: "city",
        header: "City",
        render: (order) => order.shipping_city || "—",
        hideOnMobile: true,
      },
      {
        key: "created",
        header: "Placed",
        render: (order) => formatDateTime(order.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminOrderListItem>[] = useMemo(
    () =>
      (["CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"] as const).map((key) => ({
        key,
        label: key === "CANCELLED" ? "Cancel" : ORDER_STATUS_LABELS[key],
        icon:
          key === "CANCELLED"
            ? "cancel"
            : key === "CONFIRMED"
              ? "check_circle"
              : key === "PROCESSING"
                ? "sync"
                : key === "SHIPPED"
                  ? "local_shipping"
                  : "task_alt",
        tone: key === "CANCELLED" ? ("danger" as const) : ("primary" as const),
        onClick: (order: AdminOrderListItem) => {
          const descriptor = getAvailableOrderActions(order, user).find((a) => a.status === key);
          if (descriptor) requestAction(order, descriptor);
        },
        isHidden: (order: AdminOrderListItem) =>
          !getAvailableOrderActions(order, user).some((a) => a.status === key),
      })),
    [user, requestAction]
  );

  if (!canView) {
    return <OrderAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Orders</h1>
        <p className="text-xs text-ink-muted">
          Track fulfillment across the platform and transition order status.
        </p>
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} order{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by order number…"
          value={searchInput}
          onChange={setSearchInput}
        />
        <AdminSelectField
          label="Status"
          value={urlStatus}
          options={ORDER_STATUS_OPTIONS}
          onChange={(value) => updateParams({ status: value || null, page: null })}
        />
        <AdminSelectField
          label="Payment"
          value={urlPaymentStatus}
          options={PAYMENT_STATUS_OPTIONS}
          onChange={(value) => updateParams({ payment_status: value || null, page: null })}
        />
        <AdminDateField
          label="From"
          value={urlStartDate}
          max={urlEndDate || undefined}
          onChange={(value) => updateParams({ start_date: value || null, page: null })}
        />
        <AdminDateField
          label="To"
          value={urlEndDate}
          min={urlStartDate || undefined}
          onChange={(value) => updateParams({ end_date: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminOrderListItem>
        caption="Platform orders"
        columns={columns}
        rows={orders}
        getRowId={(order) => order.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchOrders}
        emptyTitle="No orders found"
        emptyMessage={
          isFiltered ? "No orders match the current filters." : "No orders have been placed yet."
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
        open={Boolean(pendingAction && targetOrder)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetOrder && pendingAction ? pendingAction.confirmMessage(targetOrder) : ""}
            {submitError && <p className="mt-2 font-semibold text-red-600">{submitError}</p>}
          </>
        }
        confirmLabel={pendingAction?.label ?? "Confirm"}
        destructive={pendingAction?.destructive ?? false}
        requireReason
        reasonLabel="Note (optional)"
        reasonPlaceholder="Add an operational note for this transition…"
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
