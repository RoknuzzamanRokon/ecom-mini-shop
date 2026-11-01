"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  AdminApiError,
  getMyOnboardedSellers,
  getMyOnboardingSummary,
  type AdminOnboarderSummary,
  type AdminOnboardingSeller,
  type AdminPointSaleResult,
} from "@/lib/admin-api";
import { formatCount, formatDate } from "@/lib/admin-format";
import {
  AdminDataTable,
  AdminStatCard,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import { useLatestRequest } from "@/hooks/useLatestRequest";
import { pageNumber } from "@/lib/params";
import { SELLER_STATUS_LABELS, SELLER_TYPE_LABELS } from "../sellers/sellerGovernance";
import SellPointsDialog from "./SellPointsDialog";
import { canBuyPoints, saleSummary } from "./pointSale";

/** DRF's default PAGE_SIZE (config/settings/base.py), which the seller list uses. */
const PAGE_SIZE = 12;

export default function AdminMySellersPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-24">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      }
    >
      <AdminMySellersPageContent />
    </Suspense>
  );
}

/**
 * The Sales Team's own sellers (docs/FOLLOW_UPS_PLAN.md §5): the onboarder's
 * points and tokens, the sellers they opened, and Sell points on the approved
 * ones. Administrators and Finance sell from Users instead.
 */
function AdminMySellersPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canUse = hasAnyPermission(user, ADMIN_PERMISSIONS.sellersOnboard);
  const urlPage = pageNumber(searchParams.get("page"));

  const [summary, setSummary] = useState<AdminOnboarderSummary | null>(null);
  const [sellers, setSellers] = useState<AdminOnboardingSeller[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selling, setSelling] = useState<AdminOnboardingSeller | null>(null);

  const beginRequest = useLatestRequest();

  // State is only set in the promise callbacks; a caller that wants the
  // spinner (retry, page change) sets `loading` itself first.
  const fetchPage = useCallback((): Promise<void> => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      });
    }
    return Promise.all([getMyOnboardingSummary(token), getMyOnboardedSellers(token, { page: urlPage })])
      .then(([nextSummary, list]) => {
        if (!isLatest()) return;
        setSummary(nextSummary);
        setSellers(list.results);
        setTotalCount(list.count);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!isLatest()) return;
        setSellers([]);
        setTotalCount(0);
        setError(err instanceof Error ? err : new Error("Failed to load your sellers."));
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [urlPage, beginRequest]);

  useEffect(() => {
    if (!canUse) return;
    fetchPage();
  }, [canUse, fetchPage]);

  const reload = useCallback(() => {
    setLoading(true);
    fetchPage();
  }, [fetchPage]);

  const setWalletPoints = useCallback((points: number) => {
    setSummary((current) => (current ? { ...current, points } : current));
  }, []);

  const handleSold = useCallback(
    (result: AdminPointSaleResult) => {
      if (selling) setNotice(saleSummary(selling, result));
      setWalletPoints(result.your_points);
      setSelling(null);
    },
    [selling, setWalletPoints]
  );

  const columns: AdminTableColumn<AdminOnboardingSeller>[] = useMemo(
    () => [
      {
        key: "seller",
        header: "Seller",
        render: (seller) => (
          <>
            <span className="block font-bold text-ink line-clamp-1">{seller.business_name}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
              @{seller.username}
              {seller.phone ? ` · ${seller.phone}` : ""}
            </span>
          </>
        ),
        width: "w-56",
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
        key: "sell",
        label: "Sell points",
        icon: "add_card",
        tone: "primary",
        onClick: (seller) => {
          setNotice(null);
          setSelling(seller);
        },
        isHidden: (seller) => !canBuyPoints(seller),
        isDisabled: () => !summary || summary.points < summary.minimum_point_sale,
      },
    ],
    [summary]
  );

  if (!canUse) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
          <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            This page is for the Sales Team: it needs <code className="font-mono text-[11px]">sellers.onboard</code>.
            Administrators and Finance sell points from a seller&apos;s page under Users.
          </p>
          <Link
            href="/admin"
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Return to Overview
          </Link>
        </div>
      </div>
    );
  }

  const short = summary !== null && summary.points < summary.minimum_point_sale;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">My Sellers</h1>
        <p className="text-xs text-ink-muted">
          The sellers you onboarded. Once staff approve a seller, you can sell them points after they pay you in
          cash or bKash.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <AdminStatCard
          title="Your points"
          value={summary?.points}
          icon="account_balance_wallet"
          tone="primary"
          loading={!summary && loading}
          description={summary ? `Minimum sale: ${formatCount(summary.minimum_point_sale)} points` : undefined}
        />
        <AdminStatCard
          title="Your tokens"
          value={summary?.tokens}
          icon="token"
          tone="primary"
          loading={!summary && loading}
          description={summary ? `${formatCount(summary.tokens_per_seller)} for each seller you onboard` : undefined}
        />
        <AdminStatCard
          title="Live sellers"
          value={summary?.sellers.live}
          icon="storefront"
          tone="primary"
          loading={!summary && loading}
          description={summary ? `${formatCount(summary.sellers.awaiting_approval)} awaiting approval` : undefined}
        />
      </div>

      {short && (
        <div role="note" className="rounded-xl border border-accent/30 bg-accent/10 p-3 text-xs font-medium text-accent">
          Your wallet holds fewer points than the minimum sale of {formatCount(summary.minimum_point_sale)}. Ask an
          administrator or Finance for more points before selling.
        </div>
      )}

      {notice && (
        <div role="status" className="rounded-xl border border-success/30 bg-success/10 p-3 flex items-start gap-2">
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-success shrink-0">
            check_circle
          </span>
          <p className="text-xs font-semibold text-success">{notice}</p>
        </div>
      )}

      <AdminDataTable<AdminOnboardingSeller>
        caption="Sellers you onboarded"
        columns={columns}
        rows={sellers}
        getRowId={(seller) => seller.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={reload}
        emptyTitle="No sellers yet"
        emptyMessage="Sellers you onboard in the field appear here."
        actions={actions}
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => {
          setLoading(true);
          router.replace(page === 1 ? pathname : `${pathname}?page=${page}`);
        }}
      />

      {selling && summary && (
        <SellPointsDialog
          key={selling.id}
          seller={selling}
          minimum={summary.minimum_point_sale}
          available={summary.points}
          onClose={() => setSelling(null)}
          onSold={handleSold}
          onBalance={setWalletPoints}
        />
      )}
    </div>
  );
}
