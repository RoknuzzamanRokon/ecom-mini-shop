"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminPayment, getAdminPayments } from "@/lib/admin-api";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
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
  PAYMENT_METHOD_LABELS,
  PAYMENT_METHOD_OPTIONS,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_OPTIONS,
  PaymentAccessNotice,
  canViewAdminPayments,
  getAvailableVerifyActions,
  useVerifyPaymentAction,
} from "./paymentGovernance";

/** Matches StandardResultsSetPagination.page_size in shop/api_views.py (the backend's default). */
const PAGE_SIZE = 12;

export default function AdminPaymentsPage() {
  return (
    <Suspense fallback={<PaymentsPageFallback />}>
      <AdminPaymentsPageContent />
    </Suspense>
  );
}

function PaymentsPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminPaymentsPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminPayments(user);

  const urlSearch = searchParams.get("order_number") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  const urlMethod = searchParams.get("payment_method") ?? "";
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
        updateParams({ order_number: searchInput || null, page: null });
      }
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const [payments, setPayments] = useState<AdminPayment[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchPayments = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminPayments(token, {
        order_number: urlSearch || undefined,
        status: urlStatus || undefined,
        payment_method: urlMethod || undefined,
        page: urlPage,
      });
      setPayments(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setPayments([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load payments."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlMethod, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchPayments();
  }, [canView, fetchPayments]);

  const isFiltered = Boolean(urlSearch || urlStatus || urlMethod);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ order_number: null, status: null, payment_method: null, page: null });
  }, [updateParams]);

  const handleActionSuccess = useCallback((updated: AdminPayment) => {
    setPayments((prev) => prev.map((payment) => (payment.id === updated.id ? updated : payment)));
  }, []);
  const { pendingAction, targetPayment, submitError, requestAction, cancel, confirm } =
    useVerifyPaymentAction(handleActionSuccess);

  const columns: AdminTableColumn<AdminPayment>[] = useMemo(
    () => [
      {
        key: "payment",
        header: "Payment",
        render: (payment) => (
          <Link
            href={`/admin/payments/${payment.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1 font-mono">{payment.payment_number}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              {PAYMENT_METHOD_LABELS[payment.payment_method] ?? payment.payment_method}
            </span>
          </Link>
        ),
        width: "w-56",
      },
      {
        key: "order",
        header: "Order",
        render: (payment) => (
          <Link
            href={`/admin/orders/${payment.order_id}`}
            className="font-mono text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            {payment.order_number}
          </Link>
        ),
      },
      {
        key: "amount",
        header: "Amount",
        render: (payment) => <span className="font-bold text-ink">{formatTaka(payment.amount)}</span>,
        align: "right",
        width: "w-28",
      },
      {
        key: "refundable",
        header: "Refundable",
        render: (payment) => formatTaka(payment.refundable_amount),
        align: "right",
        hideOnMobile: true,
      },
      {
        key: "status",
        header: "Status",
        render: (payment) => (
          <AdminStatusBadge status={payment.status} label={PAYMENT_STATUS_LABELS[payment.status]} />
        ),
      },
      {
        key: "created",
        header: "Created",
        render: (payment) => formatDateTime(payment.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminPayment>[] = useMemo(
    () =>
      (["PAID", "FAILED"] as const).map((target) => ({
        key: target,
        label: target === "PAID" ? "Mark Paid" : "Mark Failed",
        icon: target === "PAID" ? "check_circle" : "cancel",
        tone: target === "PAID" ? ("primary" as const) : ("danger" as const),
        onClick: (payment: AdminPayment) => {
          const descriptor = getAvailableVerifyActions(payment, user).find((a) => a.target === target);
          if (descriptor) requestAction(payment, descriptor);
        },
        isHidden: (payment: AdminPayment) =>
          !getAvailableVerifyActions(payment, user).some((a) => a.target === target),
      })),
    [user, requestAction]
  );

  if (!canView) {
    return <PaymentAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Payments</h1>
        <p className="text-xs text-ink-muted">
          Verify transactions and process refunds across the platform.
        </p>
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} payment{totalCount === 1 ? "" : "s"}
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
          options={PAYMENT_STATUS_OPTIONS}
          onChange={(value) => updateParams({ status: value || null, page: null })}
        />
        <AdminSelectField
          label="Method"
          value={urlMethod}
          options={PAYMENT_METHOD_OPTIONS}
          onChange={(value) => updateParams({ payment_method: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminPayment>
        caption="Platform payments"
        columns={columns}
        rows={payments}
        getRowId={(payment) => payment.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchPayments}
        emptyTitle="No payments found"
        emptyMessage={
          isFiltered ? "No payments match the current filters." : "No payment records exist yet."
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
        open={Boolean(pendingAction && targetPayment)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetPayment && pendingAction ? pendingAction.confirmMessage(targetPayment) : ""}
            {submitError && <p className="mt-2 font-semibold text-red-600">{submitError}</p>}
          </>
        }
        confirmLabel={pendingAction?.label ?? "Confirm"}
        destructive={pendingAction?.destructive ?? false}
        requireReason
        reasonLabel={pendingAction?.reasonLabel ?? "Note (optional)"}
        reasonPlaceholder={pendingAction?.reasonPlaceholder}
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
