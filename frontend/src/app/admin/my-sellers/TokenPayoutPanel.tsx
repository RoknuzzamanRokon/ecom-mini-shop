"use client";

import React, { useCallback, useEffect, useId, useState } from "react";
import Dialog from "@/components/feedback/Dialog";
import { getAuthToken } from "@/lib/auth";
import {
  cancelTokenPayout,
  getMyTokenPayouts,
  requestTokenPayout,
  type AdminTokenPayout,
} from "@/lib/admin-api";
import { formatCount, formatDateTime, formatTaka } from "@/lib/admin-format";
import { AdminStatusBadge } from "@/components/admin/shared";
import { useLatestRequest } from "@/hooks/useLatestRequest";

interface TokenPayoutPanelProps {
  /** Tokens in the wallet, not counting a pending request's. */
  tokens: number;
  takaPerToken: number;
  /** The summary changed (tokens held or given back): reload it. */
  onChanged: () => void;
}

/** Payouts are whole taka. */
const taka = (amount: number) => formatTaka(amount, { decimals: 0 });

const BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

/** Why `text` cannot be asked for, or null when it can. */
export function payoutTokensError(text: string, available: number): string | null {
  if (!/^\d+$/.test(text.trim())) return "Enter a whole number of tokens.";
  const tokens = Number(text);
  if (tokens < 1) return "Ask for at least 1 token.";
  if (tokens > available) return `You hold ${formatCount(available)} tokens.`;
  return null;
}

const STATUS_LABELS: Record<AdminTokenPayout["status"], string> = {
  PENDING: "Waiting",
  ACCEPTED: "Paid",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

/**
 * Handing tokens in for real payment (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §2):
 * one request at a time; the tokens are held until an admin pays and accepts,
 * or rejects.
 */
export default function TokenPayoutPanel({ tokens, takaPerToken, onChanged }: TokenPayoutPanelProps) {
  const [payouts, setPayouts] = useState<AdminTokenPayout[]>([]);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const beginRequest = useLatestRequest();

  const fetchPayouts = useCallback((): Promise<void> => {
    const isLatest = beginRequest();
    const token = getAuthToken();
    if (!token) return Promise.resolve();
    return getMyTokenPayouts(token)
      .then((page) => {
        if (isLatest()) setPayouts(page.results);
      })
      .catch((err: unknown) => {
        if (isLatest()) setError(err instanceof Error ? err.message : "Your payout requests could not be loaded.");
      });
  }, [beginRequest]);

  useEffect(() => {
    fetchPayouts();
  }, [fetchPayouts]);

  const pending = payouts.find((payout) => payout.status === "PENDING") ?? null;

  const cancel = (payout: AdminTokenPayout) => {
    const token = getAuthToken();
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    cancelTokenPayout(token, payout.id)
      .then(() => {
        onChanged();
        return fetchPayouts();
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The request could not be cancelled."))
      .finally(() => setBusy(false));
  };

  return (
    <section aria-label="Token payouts" className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">Token payouts</h2>
          <p className="text-xs text-ink-muted mt-1">
            Hand your tokens to an admin to be paid {taka(takaPerToken)} for each. The tokens are held until the
            admin pays you and accepts.
          </p>
        </div>
        {!pending && (
          <button
            type="button"
            className={`${BUTTON} bg-primary hover:bg-primary-hover text-on-primary shadow-xs`}
            disabled={tokens < 1}
            onClick={() => {
              setError(null);
              setAsking(true);
            }}
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              payments
            </span>
            Request payment
          </button>
        )}
      </div>

      {pending && (
        <div role="status" className="rounded-xl border border-primary/30 bg-primary/10 p-3 flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-xs font-semibold text-ink flex-1">
            Waiting for an admin: {formatCount(pending.tokens)} tokens, {taka(pending.amount_taka)}, asked{" "}
            {formatDateTime(pending.created_at)}.
          </p>
          <button
            type="button"
            className={`${BUTTON} border border-line text-ink hover:bg-surface-alt`}
            disabled={busy}
            onClick={() => cancel(pending)}
          >
            Cancel request
          </button>
        </div>
      )}

      {error && (
        <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
          {error}
        </div>
      )}

      {payouts.length > 0 && (
        <ul className="divide-y divide-line border-t border-line" aria-label="Your payout requests">
          {payouts.slice(0, 5).map((payout) => (
            <li key={payout.id} className="flex items-start gap-3 py-2.5 text-xs">
              <div className="min-w-0 flex-1">
                <p className="font-bold text-ink">
                  {formatCount(payout.tokens)} tokens · {taka(payout.amount_taka)}
                </p>
                <p className="text-[11px] text-ink-muted break-words">
                  {formatDateTime(payout.created_at)}
                  {payout.decision_note ? ` · ${payout.decision_note}` : ""}
                </p>
              </div>
              <AdminStatusBadge status={payout.status} label={STATUS_LABELS[payout.status]} />
            </li>
          ))}
        </ul>
      )}

      {asking && (
        <PayoutRequestDialog
          available={tokens}
          takaPerToken={takaPerToken}
          onClose={() => setAsking(false)}
          onRequested={() => {
            setAsking(false);
            onChanged();
            fetchPayouts();
          }}
        />
      )}
    </section>
  );
}

function PayoutRequestDialog({
  available,
  takaPerToken,
  onClose,
  onRequested,
}: {
  available: number;
  takaPerToken: number;
  onClose: () => void;
  onRequested: () => void;
}) {
  const [amount, setAmount] = useState(String(available));
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const amountId = useId();
  const noteId = useId();

  const amountError = payoutTokensError(amount, available);
  const tokens = Number(amount);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const token = getAuthToken();
    if (!token || amountError || submitting) return;
    setSubmitting(true);
    setServerError(null);
    requestTokenPayout(token, tokens, note.trim())
      .then(onRequested)
      .catch((err: unknown) => setServerError(err instanceof Error ? err.message : "The request could not be sent."))
      .finally(() => setSubmitting(false));
  };

  return (
    <Dialog
      open
      onClose={onClose}
      dismissible={!submitting}
      labelledBy={titleId}
      describedBy={descriptionId}
      placement="sheet"
      zIndexClass="z-[100]"
      className="w-full sm:max-w-md bg-surface border border-line rounded-t-2xl sm:rounded-2xl shadow-lg p-6"
    >
      <form onSubmit={submit} className="space-y-4">
        <div>
          <h2 id={titleId} className="text-sm font-extrabold text-ink tracking-tight">
            Request payment for tokens
          </h2>
          <p id={descriptionId} className="text-xs text-ink-muted leading-relaxed mt-1.5">
            The tokens leave your wallet now and are held for the admins. If they reject the request, or you cancel
            it, the tokens come back.
          </p>
        </div>
        <div>
          <label htmlFor={amountId} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
            Tokens
          </label>
          <input
            id={amountId}
            type="number"
            inputMode="numeric"
            min={1}
            max={available}
            step={1}
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              setServerError(null);
            }}
            disabled={submitting}
            className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
          <p className={`text-[11px] mt-2 ${amountError ? "text-danger" : "text-ink-muted"}`}>
            {amountError ?? `Worth ${taka(tokens * takaPerToken)}; ${formatCount(available - tokens)} tokens stay with you.`}
          </p>
        </div>
        <div>
          <label htmlFor={noteId} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
            Note for the admin
          </label>
          <input
            id={noteId}
            type="text"
            maxLength={500}
            value={note}
            placeholder="e.g. bKash 017…"
            onChange={(event) => setNote(event.target.value)}
            disabled={submitting}
            className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>
        {serverError && (
          <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
            {serverError}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-3 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={Boolean(amountError) || submitting}
            className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Sending..." : amountError ? "Request payment" : `Request ${taka(tokens * takaPerToken)}`}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
