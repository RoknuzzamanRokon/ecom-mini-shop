"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  getAdminOnboardingQueue,
  type AdminOnboardingApproveResult,
  type AdminOnboardingSeller,
  type AdminOnboardingSellerDetail,
} from "@/lib/admin-api";
import { formatCount, formatDate } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import { useLatestRequest } from "@/hooks/useLatestRequest";
import { pageNumber } from "@/lib/params";
import { SELLER_STATUS_LABELS, SELLER_TYPE_LABELS } from "../sellers/sellerGovernance";
import {
  OnboardingAccessNotice,
  approvalSummary,
  canReviewOnboarding,
  rejectionSummary,
  useOnboardingDecision,
  type OnboardingDecision,
} from "./onboardingGovernance";

/** DRF's default PAGE_SIZE (config/settings/base.py), which the review queue uses. */
const PAGE_SIZE = 12;

export default function AdminOnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-24">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      }
    >
      <AdminOnboardingPageContent />
    </Suspense>
  );
}

function AdminOnboardingPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canReview = canReviewOnboarding(user);
  const urlPage = pageNumber(searchParams.get("page"));

  const [sellers, setSellers] = useState<AdminOnboardingSeller[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Only the newest request may set the list (BUG-073).
  const beginRequest = useLatestRequest();

  // State is only set in the promise callbacks; a caller that wants the
  // spinner (retry, page change) sets `loading` itself first.
  const fetchQueue = useCallback((): Promise<void> => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      });
    }
    return getAdminOnboardingQueue(token, { page: urlPage })
      .then((data) => {
        if (!isLatest()) return;
        setSellers(data.results);
        setTotalCount(data.count);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!isLatest()) return;
        setSellers([]);
        setTotalCount(0);
        setError(err instanceof Error ? err : new Error("Failed to load the onboarding queue."));
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [urlPage, beginRequest]);

  useEffect(() => {
    if (!canReview) return;
    fetchQueue();
  }, [canReview, fetchQueue]);

  const reload = useCallback(() => {
    setLoading(true);
    fetchQueue();
  }, [fetchQueue]);

  // A decided seller has left the queue, whichever way it went.
  const handleDecision = useCallback(
    (updated: AdminOnboardingSellerDetail | AdminOnboardingApproveResult, decision: OnboardingDecision) => {
      setSellers((prev) => prev.filter((seller) => seller.id !== updated.id));
      setTotalCount((count) => Math.max(0, count - 1));
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

  const columns: AdminTableColumn<AdminOnboardingSeller>[] = useMemo(
    () => [
      {
        key: "seller",
        header: "Seller",
        render: (seller) => (
          <Link
            href={`/admin/onboarding/${seller.id}`}
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
        key: "onboarded_by",
        header: "Onboarded by",
        render: (seller) => (seller.onboarded_by ? `@${seller.onboarded_by}` : "—"),
        hideOnMobile: true,
      },
      {
        key: "seller_type",
        header: "Type",
        render: (seller) => SELLER_TYPE_LABELS[seller.seller_type] ?? seller.seller_type,
        hideOnMobile: true,
      },
      {
        key: "catalog",
        header: "Shops / Products",
        render: (seller) => `${formatCount(seller.shop_count)} / ${formatCount(seller.product_count)}`,
        align: "right",
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
        key: "created",
        header: "Opened",
        render: (seller) => formatDate(seller.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminOnboardingSeller>[] = useMemo(
    () => [
      {
        key: "approve",
        label: "Approve all",
        icon: "verified",
        tone: "primary",
        onClick: (seller) => requestDecision(seller, "approve"),
      },
      {
        key: "reject",
        label: "Reject",
        icon: "cancel",
        tone: "danger",
        onClick: (seller) => requestDecision(seller, "reject"),
      },
    ],
    [requestDecision]
  );

  if (!canReview) {
    return <OnboardingAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Onboarding</h1>
        <p className="text-xs text-ink-muted">
          Sellers the Sales Team opened in the field, waiting for approval. Approving one puts the
          seller, its shops and its products live together.
        </p>
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

      <AdminDataTable<AdminOnboardingSeller>
        caption="Onboardings awaiting approval"
        columns={columns}
        rows={sellers}
        getRowId={(seller) => seller.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={reload}
        emptyTitle="Nothing to review"
        emptyMessage="No onboarded seller is waiting for approval."
        actions={actions}
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => {
          setLoading(true);
          router.replace(page === 1 ? pathname : `${pathname}?page=${page}`);
        }}
      />

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
