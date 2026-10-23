"use client";

/**
 * Points on the Console's user page: what the account holds, and giving or
 * taking back points without leaving it.
 *
 * Two wallets can belong to one account. A seller's wallet pays for product
 * listings and moves through POST /api/points/sellers/<id>/adjust/, to and from
 * the acting staff member's own wallet. A staff wallet holds the points that
 * staff hand to sellers; only a superuser moves points into or out of it
 * (POST /api/points/staff/<user_id>/transfer/). Every gate below only decides
 * what to offer; the backend makes the real decision on each request.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  adjustAdminSellerPoints,
  getAdminSellerPointHistory,
  getAdminSellerWallet,
  getAdminStaffWallet,
  getInsufficientPointsInfo,
  getMyStaffWallet,
  setAdminStaffPointExpiry,
  transferAdminStaffPoints,
  type AdminPointTransaction,
  type AdminSellerWallet,
  type AdminStaffWallet,
  type AdminUpcomingPointExpiry,
  type AdminUserDetail,
  type StaffWalletSummary,
} from "@/lib/admin-api";
import { formatCount, formatDate } from "@/lib/admin-format";
import { AdminConfirmModal } from "@/components/admin/shared";
import PointMovementList, { type PointMovementRow } from "@/components/points/PointMovementList";
import { toStaffMovementRow } from "../profile/adminProfile";
import {
  canCreditSellerPoints,
  canDebitSellerPoints,
  canViewSellerPoints,
  isCreditTransaction,
} from "../sellers/sellerGovernance";


/** Movements shown per wallet; the seller page and Django admin hold the full ledgers. */
const RECENT_LIMIT = 5;

/** One-click amounts in the give / take-back form. */
const AMOUNT_PRESETS = [10, 50, 100, 500, 1000];

const SELLER_MOVEMENT_ICONS: Record<string, string> = {
  ADMIN_CREDIT: "add_circle",
  ADMIN_DEBIT: "remove_circle",
  PRODUCT_CREATION: "inventory_2",
  BONUS: "redeem",
  REFUND: "undo",
  ADJUSTMENT: "tune",
  EXPIRY: "hourglass_bottom",
};

/** One line on when a wallet's points expire, or that they never do. */
function expiryNote(
  wallet: { points_expire: boolean; expiry_months: number; upcoming_expiries: AdminUpcomingPointExpiry[] },
  neverText: string
): string {
  if (!wallet.points_expire) return neverText;
  const next = wallet.upcoming_expiries[0];
  const rule = `Points expire ${wallet.expiry_months} months after they arrive.`;
  return next
    ? `${rule} Next: ${formatCount(next.points)} pts on ${formatDate(next.expires_at)}.`
    : rule;
}

function toSellerMovementRow(txn: AdminPointTransaction): PointMovementRow {
  return {
    id: txn.id,
    icon: SELLER_MOVEMENT_ICONS[txn.transaction_type] ?? "toll",
    title: txn.transaction_type_display,
    context: txn.actor_username ? `by @${txn.actor_username}` : null,
    reason: txn.reason,
    amount: txn.amount,
    incoming: isCreditTransaction(txn),
    balanceAfter: txn.balance_after,
    when: txn.created_at,
  };
}

type WalletKind = "seller" | "staff";
type PointAction = "CREDIT" | "DEBIT";

interface PointDraft {
  kind: WalletKind;
  action: PointAction;
}

interface PendingMove extends PointDraft {
  amount: number;
}

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const DANGER_OUTLINE_BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg border border-danger/40 text-danger hover:bg-danger/10 text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger";
const SECONDARY_BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg border border-line hover:bg-surface text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const CHIP_BUTTON =
  "px-2.5 py-1 rounded-full border border-line bg-surface hover:border-primary hover:text-primary text-[11px] font-bold text-ink-body tabular-nums transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";
const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

export interface UserPointsPanelProps {
  target: AdminUserDetail;
  actor: AuthUser | null;
}

export default function UserPointsPanel({ target, actor }: UserPointsPanelProps) {
  const canView = canViewSellerPoints(actor);
  const canGiveSeller = canCreditSellerPoints(actor);
  const canTakeSeller = canDebitSellerPoints(actor);
  const isSelf = actor?.id === target.id;
  // PointService.transfer_to_staff / reclaim_from_staff: a Django superuser,
  // never to or from their own wallet.
  const canMoveStaff = Boolean(actor?.is_superuser) && !isSelf;
  // The actor's own wallet is where given points come from and taken-back
  // points go, so it is worth a request whenever they could move any.
  const needsOwnWallet = canGiveSeller || canTakeSeller || canMoveStaff;
  const sellerId = target.seller_profile?.id ?? null;

  const [sellerWallet, setSellerWallet] = useState<AdminSellerWallet | null>(null);
  const [sellerRecent, setSellerRecent] = useState<AdminPointTransaction[]>([]);
  const [sellerCount, setSellerCount] = useState(0);
  const [staffWallet, setStaffWallet] = useState<AdminStaffWallet | null>(null);
  const [myWallet, setMyWallet] = useState<StaffWalletSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<PointDraft | null>(null);
  const [amount, setAmount] = useState("");
  const [pending, setPending] = useState<PendingMove | null>(null);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  // The value a superuser is about to give the staff wallet's expiry switch.
  const [expiryPending, setExpiryPending] = useState<boolean | null>(null);
  const [expiryError, setExpiryError] = useState<string | null>(null);

  // State is only set in the promise callbacks, so the effect below never
  // updates state synchronously; a retry flips the loading flag itself first.
  const load = useCallback(() => {
    const token = getAuthToken() ?? "";
    return Promise.all([
      sellerId !== null ? getAdminSellerWallet(token, sellerId) : Promise.resolve(null),
      sellerId !== null ? getAdminSellerPointHistory(token, sellerId) : Promise.resolve(null),
      getAdminStaffWallet(token, target.id),
      needsOwnWallet ? getMyStaffWallet(token) : Promise.resolve(null),
    ])
      .then(([seller, history, staff, mine]) => {
        setSellerWallet(seller);
        setSellerRecent(history ? history.results.slice(0, RECENT_LIMIT) : []);
        setSellerCount(history?.count ?? 0);
        setStaffWallet(staff);
        setMyWallet(mine);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : "Failed to load points.");
      })
      .finally(() => setLoading(false));
  }, [sellerId, target.id, needsOwnWallet]);

  useEffect(() => {
    if (canView) load();
  }, [canView, load]);

  const retry = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    load();
  }, [load]);

  const sellerRows = useMemo(() => sellerRecent.map(toSellerMovementRow), [sellerRecent]);
  const staffRows = useMemo(() => (staffWallet?.recent ?? []).map(toStaffMovementRow), [staffWallet]);

  const showSellerCard = sellerId !== null;
  // A staff wallet is worth showing once it has held points, or when it could.
  const showStaffCard = Boolean(staffWallet && (staffWallet.has_wallet || staffWallet.can_receive_transfers));

  const balanceOf = (kind: WalletKind): number | null =>
    kind === "seller" ? sellerWallet?.balance ?? null : staffWallet?.balance ?? null;

  /** The most a move can be: what the giver holds. The backend re-checks it under a row lock. */
  const maxFor = (move: PointDraft): number | null =>
    move.action === "CREDIT" ? myWallet?.balance ?? null : balanceOf(move.kind);

  const parsedAmount = Number(amount);
  const draftMax = draft ? maxFor(draft) : null;
  const amountIsWhole = amount.trim() !== "" && Number.isInteger(parsedAmount) && parsedAmount > 0;
  const amountOverMax = amountIsWhole && draftMax !== null && parsedAmount > draftMax;
  const amountValid = amountIsWhole && !amountOverMax;

  const startDraft = useCallback((kind: WalletKind, action: PointAction) => {
    setDraft({ kind, action });
    setAmount("");
    setMoveError(null);
    setSuccess(null);
  }, []);

  const cancelDraft = useCallback(() => {
    setDraft(null);
    setAmount("");
  }, []);

  const openConfirm = useCallback(() => {
    if (!draft || !amountValid) return;
    setMoveError(null);
    setPending({ ...draft, amount: parsedAmount });
  }, [draft, amountValid, parsedAmount]);

  const confirmMove = useCallback(
    async (reason: string) => {
      if (!pending) return;
      const token = getAuthToken();
      if (!token) {
        setMoveError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setMoveError(null);
        const payload = { action: pending.action, amount: pending.amount, reason };
        const result =
          pending.kind === "seller" && sellerId !== null
            ? await adjustAdminSellerPoints(token, sellerId, payload)
            : await transferAdminStaffPoints(token, target.id, payload);
        setPending(null);
        setDraft(null);
        setAmount("");
        setSuccess(result.message);
        // The response is authoritative; refetch rather than patch balances
        // locally. The buttons stay disabled until the new balances arrive.
        setLoading(true);
        load();
      } catch (err) {
        const insufficient = getInsufficientPointsInfo(err);
        setMoveError(
          insufficient
            ? insufficient.error
            : err instanceof AdminApiError
            ? err.message
            : "Failed to move points."
        );
      }
    },
    [pending, sellerId, target.id, load]
  );

  const cancelConfirm = useCallback(() => {
    setPending(null);
    setMoveError(null);
  }, []);

  const confirmExpiry = useCallback(
    async (reason: string) => {
      if (expiryPending === null) return;
      const token = getAuthToken();
      if (!token) {
        setExpiryError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setExpiryError(null);
        const result = await setAdminStaffPointExpiry(token, target.id, { enabled: expiryPending, reason });
        setExpiryPending(null);
        setSuccess(result.message);
        setLoading(true);
        load();
      } catch (err) {
        setExpiryError(err instanceof AdminApiError ? err.message : "Failed to change point expiry.");
      }
    },
    [expiryPending, target.id, load]
  );

  if (!canView) return null;

  const who = `@${target.username}`;
  const sellerName = target.seller_profile?.business_name ?? who;
  const myBalance = myWallet?.balance ?? null;

  /** Why a give / take-back button is disabled, or null when it is offered. */
  const lockFor = (kind: WalletKind, action: PointAction): string | null => {
    if (action === "CREDIT") {
      if (kind === "staff" && staffWallet && !staffWallet.can_receive_transfers) {
        return target.is_active
          ? `${who} cannot credit sellers, so points sent to them could never be used. Give them a role with points.add or points.adjust first.`
          : `${who} is inactive, so points sent to them could never be used.`;
      }
      if (myBalance === 0) {
        return actor?.is_superuser
          ? "Your wallet is empty. Create points with utils/add_points.py first."
          : "Your wallet is empty. Ask a superuser to send you points first.";
      }
      return null;
    }
    return balanceOf(kind) === 0 ? "Nothing to take back: this wallet is empty." : null;
  };

  const renderActions = (kind: WalletKind, offerGive: boolean, offerTake: boolean) => {
    if (!offerGive && !offerTake) return null;
    const giveLock = offerGive ? lockFor(kind, "CREDIT") : null;
    const takeLock = offerTake ? lockFor(kind, "DEBIT") : null;
    const notes = [giveLock, takeLock].filter((note): note is string => Boolean(note));
    return (
      <div className="mt-4">
        <div className="flex flex-wrap gap-2">
          {offerGive && (
            <button
              type="button"
              disabled={Boolean(giveLock) || loading}
              onClick={() => startDraft(kind, "CREDIT")}
              className={PRIMARY_BUTTON}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                add_circle
              </span>
              Give points
            </button>
          )}
          {offerTake && (
            <button
              type="button"
              disabled={Boolean(takeLock) || loading}
              onClick={() => startDraft(kind, "DEBIT")}
              className={DANGER_OUTLINE_BUTTON}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                remove_circle
              </span>
              Take back
            </button>
          )}
        </div>
        {notes.map((note) => (
          <p key={note} className="text-[11px] text-ink-muted mt-2">
            {note}
          </p>
        ))}
      </div>
    );
  };

  const renderDraftForm = (kind: WalletKind) => {
    if (!draft || draft.kind !== kind) return null;
    const giving = draft.action === "CREDIT";
    const inputId = `user-points-${kind}-amount`;
    const presets = AMOUNT_PRESETS.filter((preset) => draftMax === null || preset <= draftMax);
    return (
      <div className="mt-4 rounded-xl border border-line bg-surface p-4">
        <p className="text-[11px] font-extrabold uppercase tracking-wider text-ink mb-3">
          {giving ? "Give points" : "Take back points"}
          {draftMax !== null && (
            <span className="ml-2 font-bold normal-case tracking-normal text-ink-muted">
              {giving ? "Your wallet holds" : "This wallet holds"} {formatCount(draftMax)}
            </span>
          )}
        </p>
        <label htmlFor={inputId} className={FIELD_LABEL_CLASS}>
          Amount (points)
        </label>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <input
            id={inputId}
            type="number"
            inputMode="numeric"
            min={1}
            max={draftMax ?? undefined}
            step={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") openConfirm();
            }}
            placeholder="e.g. 100"
            className={`${FIELD_CONTROL_CLASS} sm:max-w-[10rem]`}
            aria-describedby={`${inputId}-hint`}
            autoFocus
          />
          <div className="flex gap-2">
            <button type="button" disabled={!amountValid} onClick={openConfirm} className={PRIMARY_BUTTON}>
              Continue
            </button>
            <button type="button" onClick={cancelDraft} className={SECONDARY_BUTTON}>
              Cancel
            </button>
          </div>
        </div>
        {(presets.length > 0 || (draftMax ?? 0) > 0) && (
          <div className="flex flex-wrap gap-1.5 mt-3" role="group" aria-label="Quick amounts">
            {presets.map((preset) => (
              <button key={preset} type="button" onClick={() => setAmount(String(preset))} className={CHIP_BUTTON}>
                {formatCount(preset)}
              </button>
            ))}
            {draftMax !== null && draftMax > 0 && !presets.includes(draftMax) && (
              <button type="button" onClick={() => setAmount(String(draftMax))} className={CHIP_BUTTON}>
                All {formatCount(draftMax)}
              </button>
            )}
          </div>
        )}
        <p
          id={`${inputId}-hint`}
          className={`text-[11px] mt-2 ${amount && !amountValid ? "text-danger" : "text-ink-faint"}`}
        >
          {amountOverMax
            ? `That is more than the ${formatCount(draftMax)} points ${giving ? "your wallet" : "this wallet"} holds.`
            : amount && !amountIsWhole
            ? "Enter a whole number of at least 1 point."
            : giving
            ? "The points come out of your own wallet."
            : "The points go back into your own wallet."}
        </p>
      </div>
    );
  };

  const pendingBalance = pending ? balanceOf(pending.kind) : null;
  const pendingTargetAfter =
    pending && pendingBalance !== null
      ? pending.action === "CREDIT"
        ? pendingBalance + pending.amount
        : pendingBalance - pending.amount
      : null;
  const pendingMineAfter =
    pending && myBalance !== null
      ? pending.action === "CREDIT"
        ? myBalance - pending.amount
        : myBalance + pending.amount
      : null;
  const pendingName = pending?.kind === "seller" ? sellerName : who;

  return (
    <section
      id="points"
      aria-labelledby="user-points-title"
      className="bg-surface rounded-2xl border border-line shadow-xs p-6 scroll-mt-24"
    >
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 id="user-points-title" className="text-sm font-extrabold text-ink uppercase tracking-wider">
            Points
          </h2>
          <p className="text-xs text-ink-muted mt-1 max-w-2xl">
            What this account holds, and giving or taking back points. Every move is written to the
            points ledger and the audit log with your reason.
          </p>
        </div>
        {myWallet && (
          <div className="shrink-0 inline-flex items-center gap-2 rounded-xl border border-line bg-surface-alt/60 px-3 py-2">
            <span aria-hidden="true" className="material-symbols-outlined text-accent text-[18px]">
              account_balance_wallet
            </span>
            <span className="text-[11px] font-semibold text-ink-muted">
              Your wallet{" "}
              <strong className="text-sm font-black text-ink tabular-nums">{formatCount(myWallet.balance)}</strong>{" "}
              pts
            </span>
          </div>
        )}
      </div>

      {success && (
        <div className="mb-4 rounded-xl border border-success/30 bg-success/10 p-3 flex items-start gap-2" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-success shrink-0 text-[18px]">
            check_circle
          </span>
          <p className="text-xs font-semibold text-ink">
            {success}
            {loading && <span className="block mt-0.5 font-normal text-ink-muted">Updating balances…</span>}
          </p>
        </div>
      )}

      {loading && !staffWallet && !loadError ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" aria-busy="true" aria-label="Loading points">
          {[0, 1].map((key) => (
            <div key={key} className="h-40 rounded-xl bg-surface-alt animate-pulse" />
          ))}
        </div>
      ) : loadError ? (
        <div className="rounded-xl border border-line bg-surface-alt/40 p-4 flex flex-col sm:flex-row sm:items-center gap-3" role="alert">
          <p className="text-xs text-ink-muted flex-1">
            <span className="font-bold text-ink">Couldn&apos;t load points.</span> {loadError}
          </p>
          <button type="button" onClick={retry} className={SECONDARY_BUTTON}>
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              refresh
            </span>
            Try again
          </button>
        </div>
      ) : !showSellerCard && !showStaffCard ? (
        <div className="flex items-start gap-3 rounded-xl border border-dashed border-line bg-surface-alt/40 p-4">
          <span
            aria-hidden="true"
            className="material-symbols-outlined w-10 h-10 shrink-0 rounded-xl bg-accent/15 text-accent flex items-center justify-center"
          >
            savings
          </span>
          <div className="min-w-0">
            <p className="text-xs font-bold text-ink">This account holds no points</p>
            <p className="text-[11px] text-ink-muted mt-0.5 leading-relaxed">
              Points belong to sellers, who spend them on product listings, and to staff who give them
              to sellers.{" "}
              {!target.is_active
                ? `${who} is inactive, so they cannot receive points until the account is activated again.`
                : actor?.is_superuser
                ? `To send ${who} staff points, first give them a role that can credit sellers (points.add or points.adjust).`
                : `Only a superuser can send staff points, and only to an account with a role that can credit sellers.`}
            </p>
          </div>
        </div>
      ) : (
        <div
          className={`grid grid-cols-1 gap-4 ${showSellerCard && showStaffCard ? "lg:grid-cols-2" : ""}`}
          aria-busy={loading || undefined}
        >
          {showSellerCard && (
            <WalletCard
              wide={!showStaffCard}
              icon="storefront"
              title="Seller wallet"
              subtitle={sellerName}
              balance={sellerWallet?.balance ?? null}
              figures={[
                { label: "Earned", value: sellerWallet?.total_earned },
                { label: "Spent", value: sellerWallet?.total_spent },
                { label: "Expired", value: sellerWallet?.total_expired },
              ]}
              note={
                sellerWallet
                  ? `Points pay for new product listings, ${formatCount(sellerWallet.product_creation_cost)} pts each. ` +
                    expiryNote(sellerWallet, "A Full Shop Owner's points never expire.")
                  : null
              }
              rows={sellerRows}
              rowsLabel={`Recent point movements for ${sellerName}`}
              emptyText="No point movements yet."
              footer={
                sellerCount > sellerRows.length && sellerId !== null ? (
                  <Link
                    href={`/admin/sellers/${sellerId}`}
                    className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  >
                    All {formatCount(sellerCount)} movements on the seller page
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      arrow_forward
                    </span>
                  </Link>
                ) : null
              }
            >
              {renderActions("seller", canGiveSeller, canTakeSeller)}
              {renderDraftForm("seller")}
            </WalletCard>
          )}

          {showStaffCard && staffWallet && (
            <WalletCard
              wide={!showSellerCard}
              icon="badge"
              title="Staff wallet"
              subtitle={isSelf ? `${who} (you)` : who}
              balance={staffWallet.balance}
              figures={[
                { label: "Received", value: staffWallet.received },
                { label: "Given to sellers", value: staffWallet.given_to_sellers },
                { label: "Sent to staff", value: staffWallet.sent_to_staff },
                { label: "Taken back", value: staffWallet.taken_back },
                { label: "Expired", value: staffWallet.expired },
              ]}
              note={
                (isSelf
                  ? actor?.is_superuser
                    ? "Your own wallet. Create points with utils/add_points.py, then give them to staff or sellers from their pages."
                    : "Your own wallet. A superuser sends you the points you give to sellers."
                  : "Points this account can give to sellers. Only a superuser can send or take back staff points.") +
                " " +
                expiryNote(
                  staffWallet,
                  staffWallet.can_mint
                    ? "A superuser's points never expire."
                    : "Point expiry is off for this account."
                )
              }
              rows={staffRows}
              rowsLabel={`Recent staff wallet movements for ${who}`}
              emptyText="Nothing has moved through this wallet yet."
              footer={
                staffWallet.transaction_count > staffRows.length ? (
                  <p className="text-[11px] text-ink-muted">
                    Showing the latest {staffRows.length} of {formatCount(staffWallet.transaction_count)} movements.
                  </p>
                ) : null
              }
            >
              {renderActions("staff", canMoveStaff, canMoveStaff)}
              {renderDraftForm("staff")}
              {canMoveStaff && !staffWallet.can_mint && (
                <div className="mt-3">
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => {
                      setExpiryError(null);
                      setSuccess(null);
                      setExpiryPending(!staffWallet.expiry_enabled);
                    }}
                    className={SECONDARY_BUTTON}
                  >
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      {staffWallet.expiry_enabled ? "timer_off" : "timer"}
                    </span>
                    {staffWallet.expiry_enabled ? "Turn point expiry off" : "Turn point expiry on"}
                  </button>
                </div>
              )}
            </WalletCard>
          )}
        </div>
      )}

      <AdminConfirmModal
        open={Boolean(pending)}
        title={pending?.action === "CREDIT" ? "Give Points" : "Take Back Points"}
        message={
          <>
            {pending && (
              <>
                <strong>
                  {pending.action === "CREDIT" ? "Give" : "Take back"} {formatCount(pending.amount)} points
                </strong>{" "}
                {pending.action === "CREDIT" ? "to" : "from"} <strong>{pendingName}</strong>
                {pending.kind === "seller" ? "'s seller wallet" : "'s staff wallet"}?
                <span className="block mt-2">
                  Their wallet: <strong>{pendingBalance !== null ? formatCount(pendingBalance) : "—"}</strong>
                  {pendingTargetAfter !== null && (
                    <>
                      {" "}
                      → <strong>{formatCount(Math.max(pendingTargetAfter, 0))}</strong>
                    </>
                  )}
                </span>
                <span className="block mt-1">
                  Your wallet: <strong>{myBalance !== null ? formatCount(myBalance) : "—"}</strong>
                  {pendingMineAfter !== null && (
                    <>
                      {" "}
                      → <strong>{formatCount(Math.max(pendingMineAfter, 0))}</strong>
                    </>
                  )}
                </span>
                <span className={`block mt-2 ${pending.action === "DEBIT" ? "font-semibold text-danger" : ""}`}>
                  {pending.action === "CREDIT"
                    ? "The points come out of your own wallet. The backend refuses the request if it holds too little."
                    : "The points leave their wallet and return to yours. The backend refuses the request if their wallet holds too little."}
                </span>
              </>
            )}
            {moveError && <span className="block mt-2 font-semibold text-danger">{moveError}</span>}
          </>
        }
        confirmLabel={pending?.action === "CREDIT" ? "Give points" : "Take back points"}
        destructive={pending?.action === "DEBIT"}
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the ledger and the audit log)"
        reasonPlaceholder="Explain why these points are moving…"
        onConfirm={confirmMove}
        onCancel={cancelConfirm}
      />

      <AdminConfirmModal
        open={expiryPending !== null}
        title={expiryPending ? "Turn Point Expiry On" : "Turn Point Expiry Off"}
        message={
          <>
            {expiryPending ? (
              <>
                Points in <strong>{who}</strong>&apos;s staff wallet will expire again. What they hold now
                gets a fresh {staffWallet ? staffWallet.expiry_months : 2}-month period.
              </>
            ) : (
              <>
                Points in <strong>{who}</strong>&apos;s staff wallet will stop expiring until you turn it back on.
              </>
            )}
            {expiryError && <span className="block mt-2 font-semibold text-danger">{expiryError}</span>}
          </>
        }
        confirmLabel={expiryPending ? "Turn expiry on" : "Turn expiry off"}
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this changes…"
        onConfirm={confirmExpiry}
        onCancel={() => {
          setExpiryPending(null);
          setExpiryError(null);
        }}
      />
    </section>
  );
}

function WalletCard({
  wide = false,
  icon,
  title,
  subtitle,
  balance,
  figures,
  note,
  rows,
  rowsLabel,
  emptyText,
  footer,
  children,
}: {
  /** The only card in the panel, so it spans the full width. */
  wide?: boolean;
  icon: string;
  title: string;
  subtitle: string;
  balance: number | null;
  figures: { label: string; value: number | undefined }[];
  note?: string | null;
  rows: PointMovementRow[];
  rowsLabel: string;
  emptyText: string;
  footer?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface-alt/40 p-4 sm:p-5 flex flex-col min-w-0">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="material-symbols-outlined w-10 h-10 shrink-0 rounded-xl bg-primary/10 text-primary flex items-center justify-center"
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-xs font-extrabold uppercase tracking-wider text-ink">{title}</h3>
          <p className="text-xs text-ink-muted truncate" title={subtitle}>
            {subtitle}
          </p>
        </div>
        <p className="shrink-0 text-right leading-none">
          <span className="text-3xl font-black text-ink tabular-nums">
            {balance !== null ? formatCount(balance) : "—"}
          </span>
          <span className="ml-1 text-xs font-extrabold text-accent">pts</span>
        </p>
      </div>

      <dl className={`grid grid-cols-2 gap-2 mt-4 ${wide ? "sm:grid-cols-4" : ""}`}>
        {figures.map((figure) => (
          <div key={figure.label} className="rounded-lg border border-line-subtle bg-surface px-2.5 py-2 min-w-0">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted truncate">
              {figure.label}
            </dt>
            <dd className="text-sm font-black text-ink tabular-nums mt-0.5">
              {figure.value !== undefined ? formatCount(figure.value) : "—"}
            </dd>
          </div>
        ))}
      </dl>

      {note && <p className="text-[11px] text-ink-muted mt-3 leading-relaxed">{note}</p>}

      {children}

      <div className="mt-5 pt-4 border-t border-line-subtle">
        <h4 className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-3">
          Recent movements
        </h4>
        {rows.length === 0 ? (
          <p className="text-[11px] text-ink-muted">{emptyText}</p>
        ) : (
          <PointMovementList rows={rows} label={rowsLabel} />
        )}
        {footer && <div className="mt-3">{footer}</div>}
      </div>
    </div>
  );
}
