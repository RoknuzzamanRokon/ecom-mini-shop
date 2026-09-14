"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminSeller, getAdminSellerDetail } from "@/lib/admin-api";
import { formatDateTime } from "@/lib/admin-format";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  SELLER_STATUS_LABELS,
  SELLER_TYPE_LABELS,
  SellerAccessNotice,
  canViewAdminSellers,
  getAvailableSellerActions,
  useSellerStatusAction,
} from "../sellerGovernance";

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

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading seller detail">
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

export default function AdminSellerDetailPage() {
  const params = useParams<{ id: string }>();
  const sellerId = params.id;
  const { user } = useAuth();

  const canView = canViewAdminSellers(user);

  const [seller, setSeller] = useState<AdminSeller | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchSeller = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminSellerDetail(token, sellerId);
      setSeller(data);
    } catch (err) {
      setSeller(null);
      setError(err instanceof Error ? err : new Error("Failed to load seller."));
    } finally {
      setLoading(false);
    }
  }, [sellerId]);

  useEffect(() => {
    if (!canView) return;
    fetchSeller();
  }, [canView, fetchSeller]);

  const handleActionSuccess = useCallback((updated: AdminSeller) => {
    setSeller(updated);
  }, []);
  const { pendingAction, targetSeller, submitError, requestAction, cancel, confirm } =
    useSellerStatusAction(handleActionSuccess);

  const backLink = (
    <Link
      href="/admin/sellers"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Sellers
    </Link>
  );

  if (!canView) {
    return <SellerAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !seller) {
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
              {isNotFound ? "Seller not found" : "Unable to load seller"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This seller profile does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchSeller}
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

  const availableActions = getAvailableSellerActions(seller, user);
  const sellerTypeLabel = SELLER_TYPE_LABELS[seller.seller_type] ?? seller.seller_type;
  // The admin shop list searches owner business name, so this deep link resolves
  // to exactly this seller's storefronts without inventing a new endpoint.
  const canSeeShops = hasAnyPermission(user, ADMIN_PERMISSIONS.shopsView);

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {seller.business_name}
              </h1>
              <AdminStatusBadge status={seller.status} label={SELLER_STATUS_LABELS[seller.status]} />
              {/* SellerProfile.is_operational — APPROVED or ACTIVE may sell. */}
              {seller.is_operational && (
                <AdminStatusBadge status={null} label="Operational" tone="success" />
              )}
            </div>
            <p className="text-xs text-ink-muted mt-1">
              @{seller.username} · {sellerTypeLabel}
            </p>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                storefront
              </span>
              {seller.shops_count} shop{seller.shops_count === 1 ? "" : "s"}
            </p>
          </div>

          {availableActions.length > 0 && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {availableActions.map((descriptor) => (
                <button
                  key={descriptor.action}
                  type="button"
                  onClick={() => requestAction(seller, descriptor)}
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

        {seller.description && (
          <p className="text-xs text-ink-muted leading-relaxed mt-4 pt-4 border-t border-line whitespace-pre-line">
            {seller.description}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Account holder */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Account Holder
          </h2>
          <dl>
            <InfoRow label="Username" value={seller.username || "—"} />
            <InfoRow label="Account Email" value={seller.email || "—"} />
            <InfoRow label="Seller Type" value={sellerTypeLabel} />
          </dl>
        </div>

        {/* Business & verification details */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Business Details
          </h2>
          <dl>
            <InfoRow label="Business Name" value={seller.business_name || "—"} />
            <InfoRow label="Business Email" value={seller.business_email || "—"} />
            <InfoRow label="Business Phone" value={seller.business_phone || "—"} />
            <InfoRow label="Tax ID" value={seller.tax_id || "—"} />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            These are the only verification attributes MiniShop stores on a seller profile.
          </p>
        </div>

        {/* Shop relationship */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Shops
          </h2>
          <dl>
            <InfoRow
              label="Registered Shops"
              value={`${seller.shops_count} shop${seller.shops_count === 1 ? "" : "s"}`}
            />
          </dl>
          {canSeeShops && seller.shops_count > 0 && (
            <Link
              href={`/admin/shops?search=${encodeURIComponent(seller.business_name)}`}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                storefront
              </span>
              View this seller&apos;s shops
            </Link>
          )}
        </div>

        {/* Governance metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Governance Metadata
          </h2>
          <dl>
            <InfoRow label="Applied" value={formatDateTime(seller.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(seller.updated_at)} />
            <InfoRow label="Reviewed At" value={formatDateTime(seller.reviewed_at)} />
            <InfoRow label="Approved At" value={formatDateTime(seller.approved_at)} />
            <InfoRow label="Suspended At" value={formatDateTime(seller.suspended_at)} />
            {seller.rejection_reason && (
              <InfoRow
                label="Rejection Reason"
                value={<span className="text-red-600">{seller.rejection_reason}</span>}
              />
            )}
            {seller.suspension_reason && (
              <InfoRow
                label="Suspension Reason"
                value={<span className="text-red-600">{seller.suspension_reason}</span>}
              />
            )}
          </dl>
        </div>
      </div>

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
