"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminPointAdjustmentAction,
  AdminPointTransaction,
  AdminSeller,
  AdminSellerWallet,
  adjustAdminSellerPoints,
  getAdminSellerDetail,
  getAdminSellerPointHistory,
  getAdminSellerWallet,
  getInsufficientPointsInfo,
} from "@/lib/admin-api";
import { formatCount, formatDateTime, humanizeToken } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminFilterBar,
  AdminSelectField,
  AdminStatCard,
  AdminStatusBadge,
  type AdminTableColumn,
} from "@/components/admin/shared";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  POINT_TRANSACTION_TYPE_OPTIONS,
  SELLER_STATUS_LABELS,
  SELLER_TYPE_LABELS,
  SellerAccessNotice,
  canCreditSellerPoints,
  canDebitSellerPoints,
  canViewAdminSellers,
  canViewSellerPoints,
  getAvailableSellerActions,
  isCreditTransaction,
  useSellerStatusAction,
} from "../sellerGovernance";

/** Matches DRF's default PAGE_SIZE (settings.py), which the points history endpoint uses. */
const POINT_HISTORY_PAGE_SIZE = 12;

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

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

  // ---------------------------------------------------------------------------
  // Points / Wallet (Phase 1G-C)
  // ---------------------------------------------------------------------------
  const canViewPoints = canViewSellerPoints(user);
  const canCredit = canCreditSellerPoints(user);
  const canDebit = canDebitSellerPoints(user);

  const [wallet, setWallet] = useState<AdminSellerWallet | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<AdminApiError | Error | null>(null);

  const [historyType, setHistoryType] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const [history, setHistory] = useState<AdminPointTransaction[]>([]);
  const [historyCount, setHistoryCount] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<AdminApiError | Error | null>(null);

  const fetchWallet = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setWalletLoading(false);
      setWalletError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setWalletLoading(true);
      setWalletError(null);
      const data = await getAdminSellerWallet(token, sellerId);
      setWallet(data);
    } catch (err) {
      setWallet(null);
      setWalletError(err instanceof Error ? err : new Error("Failed to load the wallet."));
    } finally {
      setWalletLoading(false);
    }
  }, [sellerId]);

  const fetchHistory = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setHistoryLoading(false);
      setHistoryError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setHistoryLoading(true);
      setHistoryError(null);
      const data = await getAdminSellerPointHistory(token, sellerId, {
        page: historyPage,
        type: historyType || undefined,
      });
      setHistory(data.results);
      setHistoryCount(data.count);
    } catch (err) {
      setHistory([]);
      setHistoryCount(0);
      setHistoryError(err instanceof Error ? err : new Error("Failed to load the transaction history."));
    } finally {
      setHistoryLoading(false);
    }
  }, [sellerId, historyPage, historyType]);

  useEffect(() => {
    if (!canViewPoints) return;
    fetchWallet();
  }, [canViewPoints, fetchWallet]);

  useEffect(() => {
    if (!canViewPoints) return;
    fetchHistory();
  }, [canViewPoints, fetchHistory]);

  /** Which adjustment panel is open, if any, before the amount is confirmed. */
  const [adjustAction, setAdjustAction] = useState<AdminPointAdjustmentAction | null>(null);
  const [adjustAmount, setAdjustAmount] = useState("");
  const [pendingAdjustment, setPendingAdjustment] = useState<{
    action: AdminPointAdjustmentAction;
    amount: number;
  } | null>(null);
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [pointsSuccessMessage, setPointsSuccessMessage] = useState<string | null>(null);

  const parsedAdjustAmount = Number(adjustAmount);
  const adjustAmountValid =
    adjustAmount.trim() !== "" && Number.isInteger(parsedAdjustAmount) && parsedAdjustAmount > 0;

  const startAdjustment = useCallback((action: AdminPointAdjustmentAction) => {
    setAdjustAction(action);
    setAdjustAmount("");
    setAdjustError(null);
    setPointsSuccessMessage(null);
  }, []);

  const cancelAdjustmentDraft = useCallback(() => {
    setAdjustAction(null);
    setAdjustAmount("");
  }, []);

  const openAdjustmentConfirm = useCallback(() => {
    if (!adjustAction || !adjustAmountValid) return;
    setAdjustError(null);
    setPendingAdjustment({ action: adjustAction, amount: parsedAdjustAmount });
  }, [adjustAction, adjustAmountValid, parsedAdjustAmount]);

  const confirmAdjustment = useCallback(
    async (reason: string) => {
      if (!pendingAdjustment) return;
      const token = getAuthToken();
      if (!token) {
        setAdjustError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setAdjustError(null);
        const result = await adjustAdminSellerPoints(token, sellerId, {
          action: pendingAdjustment.action,
          amount: pendingAdjustment.amount,
          reason,
        });
        setPendingAdjustment(null);
        setAdjustAction(null);
        setAdjustAmount("");
        setPointsSuccessMessage(result.message);
        // The backend response is authoritative — refetch rather than
        // optimistically mutate the displayed balance/ledger.
        fetchWallet();
        setHistoryPage(1);
        fetchHistory();
      } catch (err) {
        const insufficient = getInsufficientPointsInfo(err);
        setAdjustError(
          insufficient
            ? insufficient.error
            : err instanceof AdminApiError
            ? err.message
            : "Failed to adjust seller points."
        );
      }
    },
    [pendingAdjustment, sellerId, fetchWallet, fetchHistory]
  );

  const cancelAdjustmentConfirm = useCallback(() => {
    setPendingAdjustment(null);
    setAdjustError(null);
  }, []);

  const currentBalance = wallet?.balance ?? null;
  const projectedBalance =
    pendingAdjustment && currentBalance !== null
      ? pendingAdjustment.action === "CREDIT"
        ? currentBalance + pendingAdjustment.amount
        : currentBalance - pendingAdjustment.amount
      : null;

  const historyColumns: AdminTableColumn<AdminPointTransaction>[] = useMemo(
    () => [
      {
        key: "type",
        header: "Type",
        render: (row) => (
          <AdminStatusBadge
            status={null}
            label={row.transaction_type_display || humanizeToken(row.transaction_type)}
            tone={isCreditTransaction(row) ? "success" : "danger"}
          />
        ),
      },
      {
        key: "amount",
        header: "Amount",
        align: "right",
        render: (row) => (
          <span
            className={`font-bold ${isCreditTransaction(row) ? "text-emerald-600" : "text-red-600"}`}
          >
            {isCreditTransaction(row) ? "+" : "−"}
            {formatCount(row.amount)}
          </span>
        ),
      },
      {
        key: "before",
        header: "Before",
        align: "right",
        hideOnMobile: true,
        render: (row) => formatCount(row.balance_before),
      },
      {
        key: "after",
        header: "After",
        align: "right",
        render: (row) => formatCount(row.balance_after),
      },
      {
        key: "reason",
        header: "Reason",
        hideOnMobile: true,
        render: (row) => <span className="block line-clamp-2 max-w-xs">{row.reason}</span>,
      },
      {
        key: "actor",
        header: "Actor",
        hideOnMobile: true,
        render: (row) => row.actor_username || "System",
      },
      {
        key: "reference",
        header: "Reference",
        hideOnMobile: true,
        render: (row) =>
          row.reference_type
            ? `${row.reference_type}${row.reference_id ? ` #${row.reference_id}` : ""}`
            : "—",
      },
      {
        key: "date",
        header: "Date",
        hideOnMobile: true,
        render: (row) => formatDateTime(row.created_at),
      },
    ],
    []
  );

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

      {/* Points & Wallet */}
      {canViewPoints && (
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
            <div>
              <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
                Points &amp; Wallet
              </h2>
              <p className="text-xs text-ink-muted mt-1 max-w-2xl">
                The seller&apos;s point balance and full transaction ledger, resolved by the same
                points service every credit and debit request uses.
              </p>
            </div>
            {(canCredit || canDebit) && (
              <div className="flex flex-wrap gap-2 shrink-0">
                {canCredit && (
                  <button
                    type="button"
                    onClick={() => startAdjustment("CREDIT")}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary"
                  >
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      add_circle
                    </span>
                    Credit points
                  </button>
                )}
                {canDebit && (
                  <button
                    type="button"
                    onClick={() => startAdjustment("DEBIT")}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600"
                  >
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      remove_circle
                    </span>
                    Debit points
                  </button>
                )}
              </div>
            )}
          </div>

          {pointsSuccessMessage && (
            <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 flex items-start gap-2">
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px] text-emerald-600 shrink-0"
              >
                check_circle
              </span>
              <p className="text-xs font-semibold text-emerald-700">{pointsSuccessMessage}</p>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
            <AdminStatCard
              title="Current balance"
              value={currentBalance}
              icon="toll"
              tone="primary"
              loading={walletLoading}
              description={wallet ? `Wallet #${wallet.id}` : walletError ? walletError.message : undefined}
            />
          </div>

          {adjustAction && (
            <div className="mb-5 rounded-xl border border-line bg-surface-alt/40 p-4">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-ink mb-2">
                {adjustAction === "CREDIT" ? "Credit points — amount" : "Debit points — amount"}
              </p>
              <div className="flex flex-col sm:flex-row sm:items-end gap-3">
                <div className="flex-1 sm:max-w-xs">
                  <label htmlFor="points-adjust-amount" className={FIELD_LABEL_CLASS}>
                    Amount (points)
                  </label>
                  <input
                    id="points-adjust-amount"
                    type="number"
                    min={1}
                    step={1}
                    value={adjustAmount}
                    onChange={(e) => setAdjustAmount(e.target.value)}
                    placeholder="e.g. 100"
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={!adjustAmountValid}
                    onClick={openAdjustmentConfirm}
                    className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  >
                    Continue
                  </button>
                  <button
                    type="button"
                    onClick={cancelAdjustmentDraft}
                    className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg border border-line hover:bg-surface text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              {adjustAmount && !adjustAmountValid && (
                <p className="text-[11px] text-red-600 mt-1.5">
                  Enter a whole number of at least 1 point.
                </p>
              )}
            </div>
          )}

          <AdminFilterBar
            label="Transaction filters"
            isDirty={Boolean(historyType)}
            onReset={() => {
              setHistoryType("");
              setHistoryPage(1);
            }}
          >
            <AdminSelectField
              label="Transaction type"
              value={historyType}
              options={POINT_TRANSACTION_TYPE_OPTIONS}
              onChange={(value) => {
                setHistoryType(value);
                setHistoryPage(1);
              }}
              className="sm:w-64"
            />
          </AdminFilterBar>

          <div className="mt-4">
            <AdminDataTable<AdminPointTransaction>
              caption={`Point transaction history for ${seller.business_name}`}
              columns={historyColumns}
              rows={history}
              getRowId={(row) => row.id}
              loading={historyLoading}
              error={historyError ? historyError.message : null}
              onRetry={fetchHistory}
              emptyTitle="No transactions yet"
              emptyMessage="এই seller-এর কোনো points transaction এখনো নেই।"
              page={historyPage}
              pageSize={POINT_HISTORY_PAGE_SIZE}
              totalCount={historyCount}
              onPageChange={setHistoryPage}
            />
          </div>
        </div>
      )}

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

      <AdminConfirmModal
        open={Boolean(pendingAdjustment)}
        title={pendingAdjustment?.action === "CREDIT" ? "Credit Points" : "Debit Points"}
        message={
          <>
            {pendingAdjustment && (
              <>
                <strong>
                  {pendingAdjustment.action === "CREDIT" ? "Add" : "Deduct"}{" "}
                  {formatCount(pendingAdjustment.amount)} points
                </strong>{" "}
                {pendingAdjustment.action === "CREDIT" ? "to" : "from"}{" "}
                <strong>{seller.business_name}</strong>&apos;s wallet?
                <span className="block mt-2">
                  Current balance:{" "}
                  <strong>{currentBalance !== null ? formatCount(currentBalance) : "—"}</strong>
                  {projectedBalance !== null && (
                    <>
                      {" "}
                      → Resulting balance (estimated):{" "}
                      <strong>{formatCount(Math.max(projectedBalance, 0))}</strong>
                    </>
                  )}
                </span>
                {pendingAdjustment.action === "DEBIT" && (
                  <span className="block mt-2 font-semibold text-red-600">
                    This DEDUCTS points from the seller&apos;s wallet. The backend refuses the
                    request if the available balance is insufficient.
                  </span>
                )}
              </>
            )}
            {adjustError && <span className="block mt-2 font-semibold text-red-600">{adjustError}</span>}
          </>
        }
        confirmLabel={pendingAdjustment?.action === "CREDIT" ? "Credit points" : "Debit points"}
        destructive={pendingAdjustment?.action === "DEBIT"}
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log and ledger)"
        reasonPlaceholder="Explain why these points are being adjusted…"
        onConfirm={confirmAdjustment}
        onCancel={cancelAdjustmentConfirm}
      />
    </div>
  );
}
