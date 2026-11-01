"use client";

import React, { useId, useState } from "react";
import { getAuthToken } from "@/lib/auth";
import { closeEditSession, requestEditCode, verifyEditCode, type AdminEditSession } from "@/lib/admin-api";
import { cleanCode, clockTime, liveState, timeLeft } from "./editSession";

interface EditSessionPanelProps {
  sellerId: number;
  businessName: string;
  session: AdminEditSession | null;
  /** Date.now(), ticking while a code waits or editing is open. */
  now: number;
  onSession: (session: AdminEditSession) => void;
  /** False for a rejected or suspended seller, which can no longer be edited. */
  editable: boolean;
}

const BUTTON =
  "inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
const PRIMARY = `${BUTTON} bg-primary hover:bg-primary-hover text-on-primary`;
const SECONDARY = `${BUTTON} border border-line text-ink hover:bg-surface-alt`;

/**
 * The seller's consent to corrections (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md
 * §1): send a code to their account, enter the code they read out, then edit
 * until the window closes.
 */
export default function EditSessionPanel({
  sellerId,
  businessName,
  session,
  now,
  onSession,
  editable,
}: EditSessionPanelProps) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const codeId = useId();
  const state = liveState(session, now);

  const run = (call: (token: string) => Promise<AdminEditSession>) => {
    const token = getAuthToken();
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    call(token)
      .then((next) => {
        setCode("");
        onSession(next);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Something went wrong."))
      .finally(() => setBusy(false));
  };

  const cleaned = cleanCode(code);

  return (
    <section
      aria-label="Edit session"
      className={`rounded-2xl border p-4 sm:p-5 ${
        state === "open" ? "border-success/40 bg-success/10" : "border-line bg-surface"
      }`}
    >
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-extrabold text-ink tracking-tight flex items-center gap-1.5">
            <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-primary">
              {state === "open" ? "lock_open" : "lock"}
            </span>
            {state === "open" ? "Editing is open" : "Corrections need the seller's code"}
          </h2>
          <p className="text-xs text-ink-muted mt-1 leading-relaxed" role="status">
            {!editable
              ? `${businessName} can no longer be edited here.`
              : state === "open"
              ? `You can correct ${businessName} until ${clockTime(session?.expires_at ?? null)} (${timeLeft(
                  session?.expires_at ?? null,
                  now
                )} left).`
              : state === "waiting"
              ? `A code was sent to ${businessName}'s account and works until ${clockTime(
                  session?.code_expires_at ?? null
                )}. Ask them to read it to you.`
              : `We send a 6-digit code to ${businessName}'s account. Once they read it to you, you can edit for a while.`}
          </p>
        </div>
        {editable && state === "open" && (
          <button type="button" className={SECONDARY} disabled={busy} onClick={() => run((t) => closeEditSession(t, sellerId))}>
            Close editing
          </button>
        )}
        {editable && (state === "none" || state === "ended") && (
          <button type="button" className={PRIMARY} disabled={busy} onClick={() => run((t) => requestEditCode(t, sellerId))}>
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              sms
            </span>
            Send code to seller
          </button>
        )}
      </div>

      {editable && state === "waiting" && (
        <form
          className="mt-4 flex flex-col sm:flex-row sm:items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (cleaned) run((t) => verifyEditCode(t, sellerId, cleaned));
          }}
        >
          <div className="sm:w-48">
            <label htmlFor={codeId} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
              Seller&apos;s code
            </label>
            <input
              id={codeId}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={7}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                setError(null);
              }}
              disabled={busy}
              className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm tracking-[0.3em] font-mono text-ink focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <button type="submit" className={PRIMARY} disabled={busy || !cleaned}>
            Open editing
          </button>
          <button type="button" className={SECONDARY} disabled={busy} onClick={() => run((t) => requestEditCode(t, sellerId))}>
            Send a new code
          </button>
        </form>
      )}
      {error && (
        <div role="alert" className="mt-3 p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
          {error}
        </div>
      )}
    </section>
  );
}
