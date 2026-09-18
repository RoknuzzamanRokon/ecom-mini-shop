"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminPayment, AdminRefund, getAdminPaymentDetail } from "@/lib/admin-api";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
import { AdminConfirmModal, AdminDataTable, AdminStatusBadge, type AdminTableColumn } from "@/components/admin/shared";
import {
  PAYMENT_METHOD_LABELS,
  PAYMENT_STATUS_LABELS,
  canRefundAdminPayments,
  getAvailableVerifyActions,
  isRefundEligible,
  useRefundPaymentAction,
  useVerifyPaymentAction,
} from "../paymentGovernance";

const ACTION_BUTTON_TONE: Record<string, string> = {
  primary: "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
  danger: "bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600",
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-40 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value}</dd>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
      <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">{title}</h2>
      {children}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading payment detail">
      <div className="h-6 w-40 bg-surface-alt animate-pulse rounded-md" />
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[0, 1].map((i) => (
          <div key={i} className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
            <div className="h-4 w-32 bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-full bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-3/4 bg-surface-alt animate-pulse rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminPaymentDetailPage() {
  const params = useParams<{ id: string }>();
  const paymentId = params.id;
  const { user } = useAuth();

  const [payment, setPayment] = useState<AdminPayment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchPayment = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminPaymentDetail(token, paymentId);
      setPayment(data);
    } catch (err) {
      setPayment(null);
      setError(err instanceof Error ? err : new Error("Failed to load payment."));
    } finally {
      setLoading(false);
    }
  }, [paymentId]);

  useEffect(() => {
    fetchPayment();
  }, [fetchPayment]);

  const handleVerifySuccess = useCallback((updated: AdminPayment) => {
    setPayment(updated);
  }, []);
  const {
    pendingAction,
    targetPayment: verifyTarget,
    submitError: verifyError,
    requestAction,
    cancel: cancelVerify,
    confirm: confirmVerify,
  } = useVerifyPaymentAction(handleVerifySuccess);

  const handleRefundSuccess = useCallback((refreshed: AdminPayment) => {
    setPayment(refreshed);
    setRefundAmountDraft("");
  }, []);
  const [refundAmountDraft, setRefundAmountDraft] = useState("");
  const {
    targetPayment: refundTarget,
    previewAmount,
    submitError: refundError,
    open: openRefund,
    cancel: cancelRefund,
    confirm: confirmRefund,
  } = useRefundPaymentAction(handleRefundSuccess);

  const backLink = (
    <Link
      href="/admin/payments"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Payments
    </Link>
  );

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !payment) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              {isNotFound ? "search_off" : "error"}
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">
              {isNotFound ? "Payment not found" : "Unable to load payment"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This payment does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchPayment}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  const availableVerifyActions = getAvailableVerifyActions(payment, user);
  const canRefund = canRefundAdminPayments(user) && isRefundEligible(payment);
  const hasMetadata = payment.metadata && Object.keys(payment.metadata).length > 0;

  const refundColumns: AdminTableColumn<AdminRefund>[] = [
    {
      key: "refund",
      header: "Refund",
      render: (refund) => <span className="font-mono font-semibold text-ink">{refund.refund_number}</span>,
    },
    {
      key: "amount",
      header: "Amount",
      render: (refund) => <span className="font-bold text-ink">{formatTaka(refund.amount)}</span>,
      align: "right",
      width: "w-28",
    },
    {
      key: "status",
      header: "Status",
      render: (refund) => <AdminStatusBadge status={refund.status} size="sm" />,
    },
    {
      key: "reason",
      header: "Reason",
      render: (refund) => refund.reason || "—",
      hideOnMobile: true,
    },
    {
      key: "processed_by",
      header: "Processed By",
      render: (refund) => refund.processed_by_name || "—",
      hideOnMobile: true,
    },
    {
      key: "created",
      header: "Date",
      render: (refund) => formatDateTime(refund.created_at),
      hideOnMobile: true,
    },
  ];

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight font-mono break-words">
                {payment.payment_number}
              </h1>
              <AdminStatusBadge status={payment.status} label={PAYMENT_STATUS_LABELS[payment.status]} />
            </div>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                receipt_long
              </span>
              Order{" "}
              <Link
                href={`/admin/orders/${payment.order_id}`}
                className="font-mono font-semibold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
              >
                {payment.order_number}
              </Link>
            </p>
          </div>

          {availableVerifyActions.length > 0 && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {availableVerifyActions.map((descriptor) => (
                <button
                  key={descriptor.target}
                  type="button"
                  onClick={() => requestAction(payment, descriptor)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 ${ACTION_BUTTON_TONE[descriptor.tone]}`}
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    {descriptor.icon}
                  </span>
                  {descriptor.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Payment information */}
        <SectionCard title="Payment Information">
          <dl>
            <InfoRow label="Method" value={PAYMENT_METHOD_LABELS[payment.payment_method] ?? payment.payment_method} />
            <InfoRow label="Amount" value={<span className="font-bold text-ink">{formatTaka(payment.amount)}</span>} />
            <InfoRow label="Currency" value={payment.currency} />
            <InfoRow label="Refundable" value={formatTaka(payment.refundable_amount)} />
            <InfoRow label="Provider" value={payment.provider || "—"} />
            <InfoRow label="Transaction ID" value={payment.transaction_id || "—"} />
            <InfoRow label="Paid At" value={formatDateTime(payment.paid_at)} />
            {payment.failure_reason && (
              <InfoRow
                label="Failure Reason"
                value={<span className="text-red-600">{payment.failure_reason}</span>}
              />
            )}
          </dl>
        </SectionCard>

        {/* Metadata */}
        <SectionCard title="Metadata">
          {hasMetadata ? (
            <pre className="text-[11px] leading-relaxed bg-surface-alt rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
              {JSON.stringify(payment.metadata, null, 2)}
            </pre>
          ) : (
            <p className="text-xs text-ink-muted">No transaction metadata recorded.</p>
          )}
          <dl className="mt-4 pt-4 border-t border-line">
            <InfoRow label="Created" value={formatDateTime(payment.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(payment.updated_at)} />
          </dl>
        </SectionCard>
      </div>

      {/* Refunds */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
            Refunds ({payment.refunds.length})
          </h2>

          {canRefund && (
            <div className="flex flex-col sm:flex-row sm:items-end gap-2">
              <div className="w-full sm:w-44">
                <label
                  htmlFor="refund-amount"
                  className="block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5"
                >
                  Refund Amount
                </label>
                <input
                  id="refund-amount"
                  type="number"
                  min="0.01"
                  max={payment.refundable_amount}
                  step="0.01"
                  placeholder={`Full (${formatTaka(payment.refundable_amount)})`}
                  value={refundAmountDraft}
                  onChange={(e) => setRefundAmountDraft(e.target.value)}
                  className="w-full bg-surface border border-line rounded-lg px-2.5 py-2 text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
                />
              </div>
              <button
                type="button"
                onClick={() => openRefund(payment, refundAmountDraft)}
                className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  undo
                </span>
                Process Refund
              </button>
            </div>
          )}
        </div>

        <AdminDataTable<AdminRefund>
          caption={`Refunds for payment ${payment.payment_number}`}
          columns={refundColumns}
          rows={payment.refunds}
          getRowId={(refund) => refund.id}
          emptyTitle="No refunds"
          emptyMessage="No refunds have been issued for this payment."
        />
      </div>

      <AdminConfirmModal
        open={Boolean(pendingAction && verifyTarget)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {verifyTarget && pendingAction ? pendingAction.confirmMessage(verifyTarget) : ""}
            {verifyError && <p className="mt-2 font-semibold text-red-600">{verifyError}</p>}
          </>
        }
        confirmLabel={pendingAction?.label ?? "Confirm"}
        destructive={pendingAction?.destructive ?? false}
        requireReason
        reasonLabel={pendingAction?.reasonLabel ?? "Note (optional)"}
        reasonPlaceholder={pendingAction?.reasonPlaceholder}
        onConfirm={confirmVerify}
        onCancel={cancelVerify}
      />

      <AdminConfirmModal
        open={Boolean(refundTarget)}
        title="Process Refund"
        message={
          <>
            {refundTarget &&
              `Refund ${formatTaka(previewAmount)} for order "${refundTarget.order_number}"? This cannot be undone.`}
            {refundError && <p className="mt-2 font-semibold text-red-600">{refundError}</p>}
          </>
        }
        confirmLabel="Process Refund"
        destructive
        requireReason
        reasonLabel="Reason (optional)"
        reasonPlaceholder="Why is this refund being issued?"
        onConfirm={confirmRefund}
        onCancel={cancelRefund}
      />
    </div>
  );
}
