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
  acceptTokenPayout,
  getTokenPayoutQueue,
  rejectTokenPayout,
  type AdminTokenPayout,
} from "@/lib/admin-api";
import { formatCount, formatDateTime, formatTaka } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminStatCard,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import { useLatestRequest } from "@/hooks/useLatestRequest";
import { pageNumber } from "@/lib/params";

/** DRF's default PAGE_SIZE (config/settings/base.py). */
const PAGE_SIZE = 12;

const STATUS_LABELS: Record<AdminTokenPayout["status"], string> = {
  PENDING: "Waiting",
  ACCEPTED: "Paid",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

/** Payouts are whole taka. */
const taka = (amount: number) => formatTaka(amount, { decimals: 0 });

type Decision = "accept" | "reject";

export default function AdminTokenPayoutsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-24">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      }
    >
      <AdminTokenPayoutsContent />
    </Suspense>
  );
}

/**
 * The Sales Team's token payout requests (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md
 * §2). Pay the onboarder outside MiniShop, then Accept: their tokens move to
 * you. Reject gives the tokens back, with a reason they see.
 */
function AdminTokenPayoutsContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const canUse = hasAnyPermission(user, ADMIN_PERMISSIONS.tokenPayoutsManage);
  const showAll = searchParams.get("view") === "all";
  const urlPage = pageNumber(searchParams.get("page"));

  const [payouts, setPayouts] = useState<AdminTokenPayout[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [yourTokens, setYourTokens] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<{ payout: AdminTokenPayout; decision: Decision } | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const beginRequest = useLatestRequest();

  const fetchPage = useCallback((): Promise<void> => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      });
    }
    return getTokenPayoutQueue(token, { status: showAll ? undefined : "PENDING", page: urlPage })
      .then((queue) => {
        if (!isLatest()) return;
        setPayouts(queue.results);
        setTotalCount(queue.count);
        setYourTokens(queue.your_tokens);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!isLatest()) return;
        setPayouts([]);
        setTotalCount(0);
        setError(err instanceof Error ? err : new Error("Failed to load the payout requests."));
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [showAll, urlPage, beginRequest]);

  useEffect(() => {
    if (!canUse) return;
    fetchPage();
  }, [canUse, fetchPage]);

  const confirm = (reason: string) => {
    const token = getAuthToken();
    if (!token || !deciding) return;
    const { payout, decision } = deciding;
    setSubmitError(null);
    const call =
      decision === "accept" ? acceptTokenPayout(token, payout.id, reason) : rejectTokenPayout(token, payout.id, reason);
    return call
      .then((updated) => {
        setDeciding(null);
        setNotice(
          decision === "accept"
            ? `Accepted: ${formatCount(updated.tokens)} tokens from @${updated.requested_by} are now yours (${taka(
                updated.amount_taka
              )}).`
            : `Rejected: ${formatCount(updated.tokens)} tokens went back to @${updated.requested_by}.`
        );
        setLoading(true);
        return fetchPage();
      })
      .catch((err: unknown) => {
        setSubmitError(err instanceof Error ? err.message : "The decision could not be saved.");
      });
  };

  const columns: AdminTableColumn<AdminTokenPayout>[] = useMemo(
    () => [
      {
        key: "requested_by",
        header: "Onboarder",
        render: (payout) => (
          <>
            <span className="block font-bold text-ink">@{payout.requested_by}</span>
            {payout.note && <span className="block text-[11px] text-ink-muted break-words">{payout.note}</span>}
          </>
        ),
        width: "w-56",
      },
      {
        key: "amount",
        header: "Tokens / ৳",
        render: (payout) => `${formatCount(payout.tokens)} / ${taka(payout.amount_taka)}`,
        align: "right",
      },
      {
        key: "status",
        header: "Status",
        render: (payout) => <AdminStatusBadge status={payout.status} label={STATUS_LABELS[payout.status]} />,
      },
      {
        key: "decision",
        header: "Decision",
        render: (payout) =>
          payout.decided_at ? (
            <span className="text-[11px] text-ink-muted break-words">
              {payout.decided_by ? `@${payout.decided_by}, ` : ""}
              {formatDateTime(payout.decided_at)}
              {payout.decision_note ? ` · ${payout.decision_note}` : ""}
            </span>
          ) : (
            "—"
          ),
        hideOnMobile: true,
      },
      {
        key: "created",
        header: "Asked",
        render: (payout) => formatDateTime(payout.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminTokenPayout>[] = useMemo(
    () => [
      {
        key: "accept",
        label: "Accept",
        icon: "check_circle",
        tone: "primary",
        onClick: (payout) => {
          setNotice(null);
          setSubmitError(null);
          setDeciding({ payout, decision: "accept" });
        },
        isHidden: (payout) => payout.status !== "PENDING" || payout.requested_by === user?.username,
      },
      {
        key: "reject",
        label: "Reject",
        icon: "cancel",
        tone: "danger",
        onClick: (payout) => {
          setNotice(null);
          setSubmitError(null);
          setDeciding({ payout, decision: "reject" });
        },
        isHidden: (payout) => payout.status !== "PENDING" || payout.requested_by === user?.username,
      },
    ],
    [user?.username]
  );

  if (!canUse) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
          <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            Settling token payouts needs <code className="font-mono text-[11px]">onboarding.payouts.manage</code>.
          </p>
          <Link
            href="/admin"
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs"
          >
            Return to Overview
          </Link>
        </div>
      </div>
    );
  }

  const tab = (all: boolean, label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={showAll === all}
      onClick={() => {
        if (showAll === all) return;
        setLoading(true);
        router.replace(all ? `${pathname}?view=all` : pathname);
      }}
      className={`px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer ${
        showAll === all ? "bg-primary text-on-primary" : "text-ink-muted hover:text-ink"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Token Payouts</h1>
        <p className="text-xs text-ink-muted">
          The Sales Team hands in tokens to be paid for them. Pay the onboarder first, in cash or bKash, then accept:
          the tokens move to you.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AdminStatCard
          title={showAll ? "Requests" : "Waiting"}
          value={loading && !payouts.length ? undefined : totalCount}
          icon="pending_actions"
          tone="primary"
          loading={loading && !payouts.length}
        />
        <AdminStatCard
          title="Tokens you received"
          value={yourTokens ?? undefined}
          icon="toll"
          tone="primary"
          loading={yourTokens === null}
        />
      </div>

      {notice && (
        <div role="status" className="rounded-xl border border-success/30 bg-success/10 p-3 text-xs font-semibold text-success">
          {notice}
        </div>
      )}

      <div role="tablist" aria-label="Which requests" className="inline-flex gap-1 p-1 rounded-xl border border-line bg-surface">
        {tab(false, "Waiting")}
        {tab(true, "All")}
      </div>

      <AdminDataTable<AdminTokenPayout>
        caption="Token payout requests"
        columns={columns}
        rows={payouts}
        getRowId={(payout) => payout.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={() => {
          setLoading(true);
          fetchPage();
        }}
        emptyTitle={showAll ? "No requests yet" : "Nothing waiting"}
        emptyMessage="Requests from the Sales Team appear here."
        actions={actions}
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => {
          setLoading(true);
          const query = new URLSearchParams();
          if (showAll) query.set("view", "all");
          if (page > 1) query.set("page", String(page));
          router.replace(query.toString() ? `${pathname}?${query}` : pathname);
        }}
      />

      <AdminConfirmModal
        open={Boolean(deciding)}
        title={deciding?.decision === "accept" ? "Accept this payout?" : "Reject this payout?"}
        message={
          deciding ? (
            <>
              {deciding.decision === "accept"
                ? `Accept only after paying @${deciding.payout.requested_by} ${taka(
                    deciding.payout.amount_taka
                  )}. Their ${formatCount(deciding.payout.tokens)} tokens move to your wallet.`
                : `@${deciding.payout.requested_by} gets their ${formatCount(
                    deciding.payout.tokens
                  )} tokens back and sees your reason.`}
              {submitError && <p className="mt-2 font-semibold text-danger">{submitError}</p>}
            </>
          ) : (
            ""
          )
        }
        confirmLabel={deciding?.decision === "accept" ? "Accept" : "Reject"}
        destructive={deciding?.decision === "reject"}
        requireReason
        reasonRequired={deciding?.decision === "reject"}
        reasonLabel={deciding?.decision === "accept" ? "How you paid (optional)" : "Reason"}
        reasonPlaceholder={deciding?.decision === "accept" ? "e.g. bKash TrxID 8N7…" : "Tell the onboarder why…"}
        onConfirm={confirm}
        onCancel={() => setDeciding(null)}
      />
    </div>
  );
}
