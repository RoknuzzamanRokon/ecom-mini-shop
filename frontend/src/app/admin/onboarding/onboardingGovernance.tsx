"use client";

/**
 * Field-onboarding review helpers, colocated with the /admin/onboarding routes.
 *
 * The Sales Team opens a seller in the field and adds its shop and products;
 * nothing is public until staff approve. These helpers hold:
 *   - the permission gate mirroring CanApproveOnboarding,
 *   - the approve / reject catalogue and its confirmation copy,
 *   - a decision hook shared by the queue and detail pages,
 *   - the page-level access notice.
 *
 * Nothing here is a security boundary: the backend authorizes every request.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  approveAdminOnboarding,
  rejectAdminOnboarding,
  type AdminOnboardingApproveResult,
  type AdminOnboardingSeller,
  type AdminOnboardingSellerDetail,
} from "@/lib/admin-api";
import { hasEveryPermissionGroup } from "@/lib/admin-auth";
import { ONBOARDING_REVIEW_PERMISSION_GROUPS } from "@/lib/admin-navigation";

/** Mirrors CanApproveOnboarding: seller, shop and product approval, plus publishing. */
export function canReviewOnboarding(user: AuthUser | null | undefined): boolean {
  return hasEveryPermissionGroup(user, ONBOARDING_REVIEW_PERMISSION_GROUPS);
}

/** SellerProfile.AWAITING_APPROVAL_STATUSES: the only states approve and reject start from. */
export function isAwaitingApproval(seller: Pick<AdminOnboardingSeller, "status">): boolean {
  return seller.status === "PENDING" || seller.status === "UNDER_REVIEW";
}

export type OnboardingDecision = "approve" | "reject";

export interface OnboardingDecisionDescriptor {
  decision: OnboardingDecision;
  label: string;
  icon: string;
  destructive: boolean;
  requiresReason: boolean;
  confirmTitle: string;
  confirmMessage: (seller: AdminOnboardingSeller) => string;
}

export const ONBOARDING_DECISIONS: Record<OnboardingDecision, OnboardingDecisionDescriptor> = {
  approve: {
    decision: "approve",
    label: "Approve all",
    icon: "verified",
    destructive: false,
    requiresReason: false,
    confirmTitle: "Approve Onboarding",
    confirmMessage: (seller) =>
      `Approve "${seller.business_name}"? The seller, its waiting shops and its submitted products all go live together. A shop or product already rejected on its own stays rejected.`,
  },
  reject: {
    decision: "reject",
    label: "Reject",
    icon: "cancel",
    destructive: true,
    requiresReason: true,
    confirmTitle: "Reject Onboarding",
    confirmMessage: (seller) =>
      `Reject "${seller.business_name}"? Its product fees are refunded, its ${seller.starting_points} starting points go back to ${
        seller.onboarded_by ? `@${seller.onboarded_by}` : "the onboarder"
      }, and the ${seller.tokens_awarded} tokens they earned for it are taken back. The reason is shown to the seller.`,
  },
};

/**
 * "Confirm -> call the endpoint -> hand back the result" for approve and
 * reject. On failure the modal stays open with the backend's own message.
 */
export function useOnboardingDecision(
  onSuccess: (
    updated: AdminOnboardingSellerDetail | AdminOnboardingApproveResult,
    decision: OnboardingDecision
  ) => void
) {
  const [pending, setPending] = React.useState<OnboardingDecisionDescriptor | null>(null);
  const [target, setTarget] = React.useState<AdminOnboardingSeller | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const requestDecision = React.useCallback(
    (seller: AdminOnboardingSeller, decision: OnboardingDecision) => {
      setTarget(seller);
      setPending(ONBOARDING_DECISIONS[decision]);
      setSubmitError(null);
    },
    []
  );

  const cancel = React.useCallback(() => {
    setPending(null);
    setTarget(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!pending || !target) return;
      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setSubmitError(null);
        const updated =
          pending.decision === "approve"
            ? await approveAdminOnboarding(token, target.id)
            : await rejectAdminOnboarding(token, target.id, reason);
        onSuccess(updated, pending.decision);
        setPending(null);
        setTarget(null);
      } catch (err) {
        setSubmitError(err instanceof AdminApiError ? err.message : "The decision could not be saved.");
      }
    },
    [pending, target, onSuccess]
  );

  return { pending, target, submitError, requestDecision, cancel, confirm };
}

/** What an approval put live, for the notice both pages show afterwards. */
export function approvalSummary(result: AdminOnboardingApproveResult): string {
  const shops = `${result.shops_approved} shop${result.shops_approved === 1 ? "" : "s"}`;
  const products = `${result.products_published} product${result.products_published === 1 ? "" : "s"}`;
  return `"${result.business_name}" is live with ${shops} and ${products}.`;
}

/** What a rejection returned, for the same notice. */
export function rejectionSummary(seller: AdminOnboardingSellerDetail): string {
  const who = seller.onboarded_by ? `@${seller.onboarded_by}` : "the onboarder";
  return `"${seller.business_name}" was rejected. ${seller.points_returned} points went back to ${who} and ${seller.tokens_taken_back} tokens were taken back.`;
}

/**
 * Page-level "you may not open this module" panel. Hiding the sidebar entry
 * does not stop somebody typing the URL; the backend would answer 403 anyway.
 */
export function OnboardingAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-danger/10 text-danger flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Approving an onboarding puts a seller, its shops and its products live at once, so{" "}
          <strong className="text-ink">Onboarding</strong> needs seller, shop and product approval
          and product publishing (<code className="font-mono text-[11px]">sellers.approve</code>,{" "}
          <code className="font-mono text-[11px]">shops.approve</code>,{" "}
          <code className="font-mono text-[11px]">products.approve</code>,{" "}
          <code className="font-mono text-[11px]">products.publish</code>, or the matching{" "}
          <code className="font-mono text-[11px]">*.admin.manage</code> codes).
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
