"use client";

/**
 * Payment Governance feature helpers (Phase 1K).
 *
 * Colocated with the /admin/payments routes, mirroring orderGovernance.tsx /
 * shopGovernance.tsx — feature-local, not a generic shared component. Holds:
 *   - the real Payment.STATUS_CHOICES / Payment.METHOD_CHOICES labels
 *     (verified against shop/models.py),
 *   - the verify-action catalogue and confirmation copy,
 *   - two small mutation hooks (verify, refund) shared by the list and
 *     detail pages so the "confirm -> call API -> handle result" flow is
 *     written once.
 *
 * Nothing here decides payment/refund eligibility — that is
 * Payment.VALID_TRANSITIONS / payment.can_transition_to() and
 * PaymentService.process_refund()'s remaining-refundable calculation on the
 * backend. The catalogue below only decides which buttons are worth offering.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminPayment,
  AdminPaymentVerifyStatus,
  AdminRefund,
  getAdminPaymentDetail,
  refundAdminPayment,
  verifyAdminPayment,
} from "@/lib/admin-api";
import { toNumber } from "@/lib/admin-format";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/** Verbatim (value, label) pairs from Payment.STATUS_CHOICES in shop/models.py. */
export const PAYMENT_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending",
  PROCESSING: "Processing",
  PAID: "Paid",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
  REFUNDED: "Refunded",
  PARTIALLY_REFUNDED: "Partially Refunded",
};

export const PAYMENT_STATUS_OPTIONS: AdminSelectOption[] = Object.entries(
  PAYMENT_STATUS_LABELS
).map(([value, label]) => ({ value, label }));

/** Verbatim (value, label) pairs from Payment.METHOD_CHOICES in shop/models.py. */
export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  CASH_ON_DELIVERY: "Cash on Delivery",
  BKASH: "bKash",
  NAGAD: "Nagad",
  ROCKET: "Rocket",
  CARD: "Credit / Debit Card",
  ONLINE: "Online Payment",
};

export const PAYMENT_METHOD_OPTIONS: AdminSelectOption[] = Object.entries(
  PAYMENT_METHOD_LABELS
).map(([value, label]) => ({ value, label }));

export interface VerifyActionDescriptor {
  target: AdminPaymentVerifyStatus;
  label: string;
  icon: string;
  tone: "primary" | "danger";
  destructive: boolean;
  confirmTitle: string;
  confirmMessage: (payment: { payment_number: string }) => string;
  /** PAID uses this as the (optional) transaction reference; FAILED uses it as the failure reason. */
  reasonLabel: string;
  reasonPlaceholder: string;
}

/**
 * PaymentVerifySerializer only ever accepts 'PAID' or 'FAILED' as a target —
 * never PENDING/PROCESSING/CANCELLED, which this endpoint cannot set.
 */
const VERIFY_DESCRIPTORS: Record<AdminPaymentVerifyStatus, VerifyActionDescriptor> = {
  PAID: {
    target: "PAID",
    label: "Mark Paid",
    icon: "check_circle",
    tone: "primary",
    destructive: false,
    confirmTitle: "Mark Payment Paid",
    confirmMessage: (payment) =>
      `Mark payment "${payment.payment_number}" as PAID? This confirms the funds were received.`,
    reasonLabel: "Transaction Reference (optional)",
    reasonPlaceholder: "Gateway or manual transaction reference…",
  },
  FAILED: {
    target: "FAILED",
    label: "Mark Failed",
    icon: "cancel",
    tone: "danger",
    destructive: true,
    confirmTitle: "Mark Payment Failed",
    confirmMessage: (payment) => `Mark payment "${payment.payment_number}" as FAILED?`,
    reasonLabel: "Failure Reason (optional)",
    reasonPlaceholder: "Why did this payment fail?",
  },
};

/**
 * UI-only guidance on which verify targets to OFFER for a payment's current
 * status. Mirrors Payment.VALID_TRANSITIONS in shop/models.py restricted to
 * the two targets this endpoint can ever set: PAID and FAILED are only
 * reachable from PENDING or PROCESSING. Once a payment is FAILED, CANCELLED,
 * PAID, REFUNDED, or PARTIALLY_REFUNDED, neither target is reachable through
 * this endpoint — the backend independently re-validates via
 * payment.can_transition_to(), so an incorrect entry here can only hide a
 * button, never approve an invalid mutation.
 */
function isVerifyPermitted(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.paymentsVerify);
}

export function getAvailableVerifyActions(
  payment: AdminPayment,
  user: AuthUser | null | undefined
): VerifyActionDescriptor[] {
  if (!isVerifyPermitted(user)) return [];
  if (payment.status !== "PENDING" && payment.status !== "PROCESSING") return [];
  return [VERIFY_DESCRIPTORS.PAID, VERIFY_DESCRIPTORS.FAILED];
}

/** Mirrors CanVerifyPayment exactly: 'payments.verify' or 'payments.process'. */
export function canVerifyAdminPayments(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.paymentsVerify);
}

/** Mirrors CanRefundPayment exactly: 'payments.refund' or 'orders.refund'. */
export function canRefundAdminPayments(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.paymentsRefund);
}

/**
 * UI-only guidance on refund eligibility, mirroring
 * PaymentService.process_refund()'s own gate (status must be PAID or
 * PARTIALLY_REFUNDED, and remaining_refundable must be > 0). The backend
 * recomputes remaining_refundable itself from the Refund ledger under a row
 * lock — this never trusts refundable_amount as more than a display hint for
 * whether to show the button.
 */
export function isRefundEligible(payment: AdminPayment): boolean {
  return (
    (payment.status === "PAID" || payment.status === "PARTIALLY_REFUNDED") &&
    toNumber(payment.refundable_amount) > 0
  );
}

/**
 * Shared "confirm -> call the real endpoint -> surface the result" flow for
 * payment verification, used by both the list and detail pages. Mirrors
 * useOrderStatusAction / useShopStatusAction. The verify endpoint returns the
 * full updated Payment, so `onSuccess` can be used for a wholesale replace —
 * no partial-field merge, unlike Orders' list-page staleness gap (Known
 * Issues #17).
 */
export function useVerifyPaymentAction(onSuccess: (updated: AdminPayment) => void) {
  const [pendingAction, setPendingAction] = React.useState<VerifyActionDescriptor | null>(null);
  const [targetPayment, setTargetPayment] = React.useState<AdminPayment | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestAction = React.useCallback(
    (payment: AdminPayment, descriptor: VerifyActionDescriptor) => {
      setTargetPayment(payment);
      setPendingAction(descriptor);
      setSubmitError(null);
    },
    []
  );

  const cancel = React.useCallback(() => {
    setPendingAction(null);
    setTargetPayment(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (note: string) => {
      if (!pendingAction || !targetPayment) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      try {
        setSubmitError(null);
        const updated = await verifyAdminPayment(token, targetPayment.id, {
          status: pendingAction.target,
          transaction_id: pendingAction.target === "PAID" ? note || undefined : undefined,
          reason: pendingAction.target === "FAILED" ? note || undefined : undefined,
        });
        onSuccess(updated);
        setPendingAction(null);
        setTargetPayment(null);
      } catch (err) {
        setSubmitError(
          err instanceof AdminApiError ? err.message : "Failed to update payment status."
        );
      }
    },
    [pendingAction, targetPayment, onSuccess]
  );

  return { pendingAction, targetPayment, submitError, requestAction, cancel, confirm };
}

// A typed refund amount: digits, optionally with up to two decimals. Nothing
// else (no grouping commas, no second point) is guessed at.
const REFUND_AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

/**
 * Reads a partial refund amount. Anything that is not a plain positive number
 * within the refundable balance is an error, never a silent full refund
 * (BUG-076).
 */
export function parseRefundAmount(
  input: string,
  refundable: number
): { amount: number; error: null } | { amount: null; error: string } {
  const text = input.trim();
  if (!text) return { amount: null, error: "Enter the amount to refund." };
  if (!REFUND_AMOUNT_PATTERN.test(text)) {
    return { amount: null, error: "Use digits only, with up to two decimals (for example 1500 or 1500.50)." };
  }
  const amount = Number(text);
  if (amount <= 0) return { amount: null, error: "The amount must be greater than zero." };
  if (amount > refundable) {
    return { amount: null, error: `At most ${refundable.toFixed(2)} can be refunded.` };
  }
  return { amount, error: null };
}

/** What the operator asked for: the full refundable balance, or a typed amount. */
export interface RefundRequest {
  full: boolean;
  amountInput: string;
}

function newRefundAttemptKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Shared refund flow. Unlike verify, the refund endpoint returns only the
 * created Refund — not the updated Payment — so after a refund this re-fetches
 * the full payment (getAdminPaymentDetail) rather than guessing the new
 * status/refundable_amount client-side.
 *
 * The refund and the re-fetch are separate steps (BUG-036): once the refund
 * POST succeeds the modal closes, and the caller hears about the refund even
 * if the re-fetch fails (`refreshed` is then null). Each opened refund carries
 * one idempotency key, so retrying after an unclear failure can never refund
 * twice.
 */
export function useRefundPaymentAction(
  onRefunded: (result: { refund: AdminRefund; refreshed: AdminPayment | null }) => void
) {
  const [targetPayment, setTargetPayment] = React.useState<AdminPayment | null>(null);
  const [request, setRequest] = React.useState<RefundRequest>({ full: true, amountInput: "" });
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const attemptKey = React.useRef("");

  const open = React.useCallback((payment: AdminPayment, refundRequest: RefundRequest) => {
    setTargetPayment(payment);
    setRequest(refundRequest);
    setSubmitError(null);
    attemptKey.current = newRefundAttemptKey();
  }, []);

  const cancel = React.useCallback(() => {
    setTargetPayment(null);
    setRequest({ full: true, amountInput: "" });
    setSubmitError(null);
    attemptKey.current = "";
  }, []);

  /** Display-only preview of what will be refunded; the backend computes the real amount. */
  const previewAmount = React.useMemo(() => {
    if (!targetPayment) return 0;
    const refundable = toNumber(targetPayment.refundable_amount);
    if (request.full) return refundable;
    return parseRefundAmount(request.amountInput, refundable).amount ?? 0;
  }, [request, targetPayment]);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!targetPayment) return;

      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }

      let amount: number | undefined;
      if (!request.full) {
        const parsed = parseRefundAmount(request.amountInput, toNumber(targetPayment.refundable_amount));
        if (parsed.amount === null) {
          setSubmitError(parsed.error);
          return;
        }
        amount = parsed.amount;
      }

      let refund: AdminRefund;
      try {
        setSubmitError(null);
        refund = await refundAdminPayment(token, targetPayment.id, {
          amount,
          reason: reason || undefined,
          idempotency_key: attemptKey.current,
        });
      } catch (err) {
        // The modal stays open with the same key, so a retry is safe.
        setSubmitError(err instanceof AdminApiError ? err.message : "Failed to process refund.");
        return;
      }

      // The money has moved: close the modal before anything else can fail.
      const paymentId = targetPayment.id;
      setTargetPayment(null);
      setRequest({ full: true, amountInput: "" });
      attemptKey.current = "";

      let refreshed: AdminPayment | null = null;
      try {
        refreshed = await getAdminPaymentDetail(token, paymentId);
      } catch {
        refreshed = null;
      }
      onRefunded({ refund, refreshed });
    },
    [targetPayment, request, onRefunded]
  );

  return { targetPayment, previewAmount, submitError, open, cancel, confirm };
}

/**
 * Page access gate, mirroring CanViewPayment ('payments.view', plus the
 * superuser / SUPER_ADMINISTRATOR bypass hasAnyPermission already applies).
 * Being a management user is NOT sufficient — AdminGuard only establishes
 * console eligibility.
 */
export function canViewAdminPayments(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.paymentsView);
}

/**
 * Page-level "you may not open this module" panel. Hiding the sidebar entry
 * does not stop somebody typing the URL, so the page renders this instead of
 * its data when the operator lacks the view permission. UX courtesy only:
 * the backend would return 403 for the request regardless.
 */
export function PaymentAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">
          Insufficient Permissions
        </h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Your account does not hold the permissions required to open{" "}
          <strong className="text-ink">Payments</strong>. Payment records require{" "}
          <code className="font-mono text-[11px]">payments.view</code>. Contact a Super
          Administrator if you believe this is incorrect.
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
