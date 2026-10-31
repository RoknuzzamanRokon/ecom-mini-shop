"use client";

import React, { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { formatImageUrl } from "@/lib/api";
import {
  AdminApiError,
  getAdminOnboardingDetail,
  type AdminOnboardingApproveResult,
  type AdminOnboardingSellerDetail,
  type AdminOnboardingShop,
} from "@/lib/admin-api";
import { formatCount, formatDateTime, formatTaka } from "@/lib/admin-format";
import { formatBangladeshiMobile } from "@/lib/phone";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import { SELLER_STATUS_LABELS, SELLER_TYPE_LABELS } from "../../sellers/sellerGovernance";
import {
  ONBOARDING_DECISIONS,
  OnboardingAccessNotice,
  approvalSummary,
  canReviewOnboarding,
  isAwaitingApproval,
  rejectionSummary,
  useOnboardingDecision,
  type OnboardingDecision,
} from "../onboardingGovernance";

const BUTTON_CLASS =
  "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2";

const BUTTON_TONE: Record<OnboardingDecision, string> = {
  approve: "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
  reject: "border border-danger/40 text-danger hover:bg-danger/10 focus-visible:outline-danger",
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-36 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value || "—"}</dd>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6">
      <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">{title}</h2>
      {children}
    </section>
  );
}

function ShopCard({ shop }: { shop: AdminOnboardingShop }) {
  const hasLocation = shop.latitude !== null && shop.longitude !== null;
  return (
    <section
      aria-label={shop.name}
      className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-black text-ink break-words">{shop.name}</h3>
            <AdminStatusBadge status={shop.status} />
          </div>
          <p className="text-xs text-ink-muted mt-1 break-words">
            {[shop.address, shop.phone].filter(Boolean).join(" · ") || "No address or phone given."}
          </p>
          {shop.rejection_reason && (
            <p className="text-xs text-danger mt-1">Rejected: {shop.rejection_reason}</p>
          )}
        </div>
        {hasLocation && (
          <a
            href={`https://www.google.com/maps?q=${shop.latitude},${shop.longitude}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline shrink-0"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              location_on
            </span>
            View on map
          </a>
        )}
      </div>

      {shop.products.length === 0 ? (
        <p className="text-xs text-ink-muted mt-4 pt-4 border-t border-line">No products added yet.</p>
      ) : (
        <ul className="mt-4 pt-2 border-t border-line divide-y divide-line">
          {shop.products.map((product) => (
            <li key={product.id} className="flex items-center gap-3 py-3">
              <Image
                src={formatImageUrl(product.image_url)}
                alt=""
                width={48}
                height={48}
                className="w-12 h-12 shrink-0 rounded-lg object-cover border border-line bg-surface-alt"
              />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold text-ink break-words">{product.name}</p>
                <p className="text-[11px] text-ink-muted">
                  {product.category ?? "No category"} · {formatCount(product.stock)} in stock
                </p>
                {product.rejection_reason && (
                  <p className="text-[11px] text-danger">Rejected: {product.rejection_reason}</p>
                )}
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className="text-xs font-bold text-ink">{formatTaka(product.price)}</span>
                <AdminStatusBadge status={product.status} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function AdminOnboardingDetailPage() {
  const params = useParams<{ id: string }>();
  const sellerId = params.id;
  const { user } = useAuth();
  const canReview = canReviewOnboarding(user);

  const [seller, setSeller] = useState<AdminOnboardingSellerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // State is only set in the promise callbacks; Try Again sets `loading` itself first.
  const fetchSeller = useCallback((): Promise<void> => {
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      });
    }
    return getAdminOnboardingDetail(token, sellerId)
      .then((data) => {
        setSeller(data);
        setError(null);
      })
      .catch((err: unknown) => {
        setSeller(null);
        setError(err instanceof Error ? err : new Error("Failed to load the onboarding."));
      })
      .finally(() => setLoading(false));
  }, [sellerId]);

  useEffect(() => {
    if (!canReview) return;
    fetchSeller();
  }, [canReview, fetchSeller]);

  const handleDecision = useCallback(
    (updated: AdminOnboardingSellerDetail | AdminOnboardingApproveResult, decision: OnboardingDecision) => {
      setSeller(updated);
      setNotice(
        decision === "approve"
          ? approvalSummary(updated as AdminOnboardingApproveResult)
          : rejectionSummary(updated)
      );
    },
    []
  );
  const { pending, target, submitError, requestDecision, cancel, confirm } =
    useOnboardingDecision(handleDecision);

  const backLink = (
    <Link
      href="/admin/onboarding"
      className="inline-flex items-center gap-1 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
        arrow_back
      </span>
      Back to Onboarding
    </Link>
  );

  if (!canReview) {
    return <OnboardingAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading onboarding">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
          <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
          <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
        </div>
      </div>
    );
  }

  if (error || !seller) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <span aria-hidden="true" className="material-symbols-outlined text-[26px] text-danger">
            {isNotFound ? "search_off" : "error"}
          </span>
          <p className="text-sm font-bold text-ink">
            {isNotFound ? "Onboarding not found" : "Unable to load the onboarding"}
          </p>
          <p className="text-xs text-ink-muted max-w-md">
            {isNotFound
              ? "No seller opened through field onboarding has this id."
              : error?.message || "An unexpected error occurred."}
          </p>
          {!isNotFound && (
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                fetchSeller();
              }}
              className={`${BUTTON_CLASS} ${BUTTON_TONE.approve}`}
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  const awaiting = isAwaitingApproval(seller);
  const fullName = [seller.first_name, seller.last_name].filter(Boolean).join(" ");

  return (
    <div className="space-y-6">
      {backLink}

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {seller.business_name}
              </h1>
              <AdminStatusBadge status={seller.status} label={SELLER_STATUS_LABELS[seller.status]} />
            </div>
            <p className="text-xs text-ink-muted mt-1">
              @{seller.username} · {SELLER_TYPE_LABELS[seller.seller_type] ?? seller.seller_type}
            </p>
            <p className="text-[11px] text-ink-muted mt-2">
              Onboarded by {seller.onboarded_by ? `@${seller.onboarded_by}` : "—"} on{" "}
              {formatDateTime(seller.created_at)}
            </p>
          </div>

          {awaiting && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {(["approve", "reject"] as const).map((decision) => (
                <button
                  key={decision}
                  type="button"
                  onClick={() => requestDecision(seller, decision)}
                  className={`${BUTTON_CLASS} ${BUTTON_TONE[decision]}`}
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    {ONBOARDING_DECISIONS[decision].icon}
                  </span>
                  {ONBOARDING_DECISIONS[decision].label}
                </button>
              ))}
            </div>
          )}
        </div>
        {seller.rejection_reason && (
          <p className="text-xs text-danger mt-4 pt-4 border-t border-line">
            Rejected: {seller.rejection_reason}
          </p>
        )}
      </div>

      {notice && (
        <div
          role="status"
          className="rounded-xl border border-success/30 bg-success/10 p-3 flex items-start gap-2"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-success shrink-0">
            check_circle
          </span>
          <p className="text-xs font-semibold text-success">{notice}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Account">
          <dl>
            <InfoRow label="Username" value={`@${seller.username}`} />
            <InfoRow label="Name" value={fullName} />
            <InfoRow label="Mobile (sign-in)" value={seller.phone && formatBangladeshiMobile(seller.phone)} />
            <InfoRow label="Email" value={seller.email} />
          </dl>
        </Card>
        <Card title="Business">
          <dl>
            <InfoRow label="Business phone" value={seller.business_phone} />
            <InfoRow label="Business email" value={seller.business_email} />
            <InfoRow label="Tax ID" value={seller.tax_id} />
            <InfoRow label="Description" value={seller.description} />
          </dl>
        </Card>
        <Card title="Points & Tokens">
          <dl>
            <InfoRow label="Starting points" value={formatCount(seller.starting_points)} />
            <InfoRow label="Points left" value={formatCount(seller.points_balance)} />
            <InfoRow label="Tokens earned" value={formatCount(seller.tokens_awarded)} />
            {seller.reversed_at && (
              <InfoRow
                label="Returned"
                value={`${formatCount(seller.points_returned)} points, ${formatCount(
                  seller.tokens_taken_back
                )} tokens on ${formatDateTime(seller.reversed_at)}`}
              />
            )}
            {seller.approved_at && (
              <InfoRow label="Approved" value={formatDateTime(seller.approved_at)} />
            )}
          </dl>
        </Card>
      </div>

      <div className="space-y-4">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
          Shops ({formatCount(seller.shops.length)})
        </h2>
        {seller.shops.length === 0 ? (
          <p className="text-xs text-ink-muted">No shop added yet.</p>
        ) : (
          seller.shops.map((shop) => <ShopCard key={shop.id} shop={shop} />)
        )}
      </div>

      <AdminConfirmModal
        open={Boolean(pending && target)}
        title={pending?.confirmTitle ?? ""}
        message={
          <>
            {target && pending ? pending.confirmMessage(target) : ""}
            {submitError && <p className="mt-2 font-semibold text-danger">{submitError}</p>}
          </>
        }
        confirmLabel={pending?.label ?? "Confirm"}
        destructive={pending?.destructive ?? false}
        requireReason={pending?.requiresReason ?? false}
        reasonRequired={pending?.requiresReason ?? false}
        reasonLabel="Reason"
        reasonPlaceholder="Tell the seller why the application was rejected…"
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
