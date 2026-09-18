"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminOrderDetail,
  AdminOrderItem,
  getAdminOrderDetail,
} from "@/lib/admin-api";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
import { AdminConfirmModal, AdminDataTable, AdminStatusBadge, type AdminTableColumn } from "@/components/admin/shared";
import {
  ORDER_STATUS_LABELS,
  PAYMENT_STATUS_LABELS,
  getAllowedOrderActions,
  useOrderStatusAction,
} from "../orderGovernance";

const ACTION_BUTTON_TONE: Record<string, string> = {
  primary: "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
  danger: "bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600",
  default: "border border-line text-ink hover:bg-surface-alt focus-visible:outline-primary",
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
    <div className="space-y-6" aria-busy="true" aria-label="Loading order detail">
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

export default function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = params.id;
  const { user } = useAuth();

  const [order, setOrder] = useState<AdminOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchOrder = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminOrderDetail(token, orderId);
      setOrder(data);
    } catch (err) {
      setOrder(null);
      setError(err instanceof Error ? err : new Error("Failed to load order."));
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    fetchOrder();
  }, [fetchOrder]);

  const handleActionSuccess = useCallback((updated: AdminOrderDetail) => {
    setOrder(updated);
  }, []);
  const { pendingAction, targetOrder, submitError, requestAction, cancel, confirm } =
    useOrderStatusAction<AdminOrderDetail>(handleActionSuccess);

  const backLink = (
    <Link
      href="/admin/orders"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Orders
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

  if (error || !order) {
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
              {isNotFound ? "Order not found" : "Unable to load order"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This order does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchOrder}
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

  const availableActions = getAllowedOrderActions(order, user);
  const address = order.shipping_address;

  const itemColumns: AdminTableColumn<AdminOrderItem>[] = [
    {
      key: "product",
      header: "Product",
      render: (item) => (
        <div className="min-w-0">
          <span className="block line-clamp-1 font-semibold text-ink">{item.product_name}</span>
          {item.shop_name && (
            <span className="block text-[11px] text-ink-muted line-clamp-1">{item.shop_name}</span>
          )}
        </div>
      ),
    },
    {
      key: "unit_price",
      header: "Unit Price",
      render: (item) => formatTaka(item.unit_price),
      align: "right",
      hideOnMobile: true,
    },
    {
      key: "quantity",
      header: "Qty",
      render: (item) => item.quantity,
      align: "right",
      width: "w-16",
    },
    {
      key: "line_total",
      header: "Line Total",
      render: (item) => <span className="font-bold text-ink">{formatTaka(item.line_total)}</span>,
      align: "right",
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
                {order.order_number}
              </h1>
              <AdminStatusBadge status={order.status} label={ORDER_STATUS_LABELS[order.status]} />
            </div>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                schedule
              </span>
              Placed {formatDateTime(order.created_at)}
            </p>
          </div>

          {availableActions.length > 0 && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {availableActions.map((descriptor) => (
                <button
                  key={descriptor.status}
                  type="button"
                  onClick={() => requestAction(order, descriptor)}
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
        {/* Customer */}
        <SectionCard title="Customer">
          <dl>
            <InfoRow label="Name" value={order.customer.name || "—"} />
            <InfoRow label="Username" value={order.customer.username || "Guest checkout"} />
            <InfoRow label="Email" value={order.customer.email || "—"} />
            <InfoRow label="Phone" value={order.customer.phone || "—"} />
          </dl>
        </SectionCard>

        {/* Delivery */}
        <SectionCard title="Delivery">
          <dl>
            <InfoRow label="Recipient" value={address.recipient_name || "—"} />
            <InfoRow label="Phone" value={address.phone || "—"} />
            <InfoRow
              label="Address"
              value={
                [address.address_line_1, address.address_line_2].filter(Boolean).join(", ") || "—"
              }
            />
            <InfoRow
              label="Area / City"
              value={[address.area, address.city].filter(Boolean).join(", ") || "—"}
            />
            <InfoRow
              label="State / Postcode"
              value={[address.state, address.postal_code].filter(Boolean).join(", ") || "—"}
            />
            <InfoRow label="Country" value={address.country || "—"} />
          </dl>
        </SectionCard>
      </div>

      {/* Items */}
      <div className="space-y-3">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
          Items ({order.total_items_count})
        </h2>
        <AdminDataTable<AdminOrderItem>
          caption={`Items in order ${order.order_number}`}
          columns={itemColumns}
          rows={order.items}
          getRowId={(item) => item.id}
          emptyTitle="No items"
          emptyMessage="This order has no line items."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Totals */}
        <SectionCard title="Totals">
          <dl>
            <InfoRow label="Subtotal" value={formatTaka(order.subtotal)} />
            <InfoRow label="Discount" value={`- ${formatTaka(order.discount_total)}`} />
            <InfoRow label="Shipping Fee" value={formatTaka(order.shipping_fee)} />
            <InfoRow
              label="Grand Total"
              value={<span className="font-bold text-ink">{formatTaka(order.total_amount)}</span>}
            />
          </dl>
        </SectionCard>

        {/* Payment */}
        <SectionCard title="Payment">
          {order.payment ? (
            <dl>
              <InfoRow
                label="Status"
                value={
                  <AdminStatusBadge
                    status={order.payment.status}
                    label={PAYMENT_STATUS_LABELS[order.payment.status]}
                  />
                }
              />
              <InfoRow label="Method" value={order.payment.payment_method || "—"} />
              <InfoRow label="Amount" value={formatTaka(order.payment.amount)} />
              <InfoRow label="Payment Number" value={order.payment.payment_number || "—"} />
              <InfoRow label="Transaction ID" value={order.payment.transaction_id || "—"} />
              <InfoRow label="Paid At" value={formatDateTime(order.payment.paid_at)} />
              {order.payment.failure_reason && (
                <InfoRow
                  label="Failure Reason"
                  value={<span className="text-red-600">{order.payment.failure_reason}</span>}
                />
              )}
            </dl>
          ) : (
            <p className="text-xs text-ink-muted">No payment has been recorded for this order.</p>
          )}

          {order.refunds.length > 0 && (
            <div className="mt-4 pt-4 border-t border-line">
              <h3 className="text-[11px] font-extrabold text-ink-muted uppercase tracking-wider mb-2">
                Refunds
              </h3>
              <dl>
                {order.refunds.map((refund) => (
                  <InfoRow
                    key={refund.id}
                    label={refund.refund_number}
                    value={
                      <span className="flex items-center gap-2 flex-wrap">
                        {formatTaka(refund.amount)}
                        <AdminStatusBadge status={refund.status} size="sm" />
                        <span className="text-ink-muted">{refund.reason || "No reason recorded"}</span>
                      </span>
                    }
                  />
                ))}
              </dl>
            </div>
          )}
        </SectionCard>

        {/* Timeline / Metadata */}
        <SectionCard title="Metadata">
          <dl>
            <InfoRow label="Order ID" value={order.id} />
            <InfoRow label="Created" value={formatDateTime(order.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(order.updated_at)} />
          </dl>
        </SectionCard>
      </div>

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
