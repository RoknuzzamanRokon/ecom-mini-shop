"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminShop, getAdminShopDetail } from "@/lib/admin-api";
import { formatDateTime } from "@/lib/admin-format";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import { CoordinateMapLink } from "@/components/location/UseCurrentLocationButton";
import {
  SHOP_STATUS_LABELS,
  getAvailableShopActions,
  useShopStatusAction,
} from "../shopGovernance";

const ACTION_BUTTON_TONE: Record<string, string> = {
  primary:
    "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
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
    <div className="space-y-6" aria-busy="true" aria-label="Loading shop detail">
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

export default function AdminShopDetailPage() {
  const params = useParams<{ id: string }>();
  const shopId = params.id;
  const { user } = useAuth();

  const [shop, setShop] = useState<AdminShop | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchShop = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminShopDetail(token, shopId);
      setShop(data);
    } catch (err) {
      setShop(null);
      setError(err instanceof Error ? err : new Error("Failed to load shop."));
    } finally {
      setLoading(false);
    }
  }, [shopId]);

  useEffect(() => {
    fetchShop();
  }, [fetchShop]);

  const handleActionSuccess = useCallback((updated: AdminShop) => {
    setShop(updated);
  }, []);
  const { pendingAction, targetShop, submitError, requestAction, cancel, confirm } =
    useShopStatusAction(handleActionSuccess);

  const backLink = (
    <Link
      href="/admin/shops"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Shops
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

  if (error || !shop) {
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
              {isNotFound ? "Shop not found" : "Unable to load shop"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This shop does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchShop}
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

  const availableActions = getAvailableShopActions(shop, user);

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {shop.name}
              </h1>
              <AdminStatusBadge status={shop.status} label={SHOP_STATUS_LABELS[shop.status]} />
            </div>
            <p className="text-xs text-ink-muted mt-1">/{shop.slug}</p>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                inventory_2
              </span>
              {shop.products_count} product{shop.products_count === 1 ? "" : "s"}
            </p>
          </div>

          {availableActions.length > 0 && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {availableActions.map((descriptor) => (
                <button
                  key={descriptor.action}
                  type="button"
                  onClick={() => requestAction(shop, descriptor)}
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

        {shop.description && (
          <p className="text-xs text-ink-muted leading-relaxed mt-4 pt-4 border-t border-line whitespace-pre-line">
            {shop.description}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Owner */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">Owner</h2>
          <dl>
            <InfoRow label="Business Name" value={shop.owner_business_name || "—"} />
            <InfoRow label="Seller ID" value={shop.owner_id} />
          </dl>
        </div>

        {/* Contact & Location */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Contact &amp; Location
          </h2>
          <dl>
            <InfoRow label="Phone" value={shop.phone || "—"} />
            <InfoRow label="Address" value={shop.address || "—"} />
            <InfoRow
              label="Coordinates"
              value={
                shop.latitude != null && shop.longitude != null ? (
                  <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-mono">
                      {shop.latitude}, {shop.longitude}
                    </span>
                    <CoordinateMapLink
                      latitude={String(shop.latitude)}
                      longitude={String(shop.longitude)}
                    />
                  </span>
                ) : (
                  <span className="text-ink-muted">
                    Not set — the shop won&apos;t appear in nearby-shop search.
                  </span>
                )
              }
            />
          </dl>
        </div>

        {/* Governance metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 lg:col-span-2">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Governance Metadata
          </h2>
          <dl>
            <InfoRow label="Created" value={formatDateTime(shop.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(shop.updated_at)} />
            <InfoRow label="Reviewed At" value={formatDateTime(shop.reviewed_at)} />
            <InfoRow label="Approved At" value={formatDateTime(shop.approved_at)} />
            <InfoRow label="Suspended At" value={formatDateTime(shop.suspended_at)} />
            {shop.rejection_reason && (
              <InfoRow
                label="Rejection Reason"
                value={<span className="text-red-600">{shop.rejection_reason}</span>}
              />
            )}
            {shop.suspension_reason && (
              <InfoRow
                label="Suspension Reason"
                value={<span className="text-red-600">{shop.suspension_reason}</span>}
              />
            )}
          </dl>
        </div>
      </div>

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
