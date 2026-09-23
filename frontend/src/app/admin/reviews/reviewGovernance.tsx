"use client";

/**
 * Review moderation feature helpers, colocated with /admin/reviews like the
 * other governance modules. It holds the filter options, the page access gate,
 * the hide/unhide action copy, and the "confirm -> call API -> merge result"
 * hook. The backend (CanModerateReviews) authorizes every request itself.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption } from "@/components/admin/shared";
import type { AuthUser } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminReview,
  AdminReviewType,
  hideAdminReview,
  unhideAdminReview,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

export const REVIEW_TYPE_TABS: { value: AdminReviewType; label: string }[] = [
  { value: "product", label: "Product reviews" },
  { value: "shop", label: "Shop reviews" },
];

export const RATING_OPTIONS: AdminSelectOption[] = ["5", "4", "3", "2", "1"].map((value) => ({
  value,
  label: `${value} star${value === "1" ? "" : "s"}`,
}));

export const VISIBILITY_OPTIONS: AdminSelectOption[] = [
  { value: "false", label: "Visible" },
  { value: "true", label: "Hidden" },
];

/** Mirrors CanModerateReviews: one permission covers reading and moderating. */
export function canModerateReviews(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.reviewsModerate);
}

export type ReviewModerationAction = "hide" | "unhide";

export const MODERATION_COPY: Record<
  ReviewModerationAction,
  { title: string; label: string; destructive: boolean; message: (review: AdminReview) => string }
> = {
  hide: {
    title: "Hide Review",
    label: "Hide",
    destructive: true,
    message: (review) =>
      `Hide ${review.author.username}'s ${review.rating}-star review of "${review.target.name}"? It disappears from the public review list and stops counting toward the rating. The author still sees it, marked as hidden, with the reason you give.`,
  },
  unhide: {
    title: "Restore Review",
    label: "Restore",
    destructive: false,
    message: (review) =>
      `Restore ${review.author.username}'s review of "${review.target.name}"? It becomes public again and counts toward the rating. The hide reason is cleared.`,
  },
};

/**
 * Shared hide/unhide flow. On success `onSuccess` gets exactly what the API
 * returned; on failure the modal stays open with the backend's own message
 * (e.g. "This review is already hidden." after another moderator acted).
 */
export function useReviewModeration(
  reviewType: AdminReviewType,
  onSuccess: (updated: AdminReview) => void
) {
  const [pending, setPending] = React.useState<{
    review: AdminReview;
    action: ReviewModerationAction;
  } | null>(null);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const request = React.useCallback((review: AdminReview, action: ReviewModerationAction) => {
    setPending({ review, action });
    setSubmitError(null);
  }, []);

  const cancel = React.useCallback(() => {
    setPending(null);
    setSubmitError(null);
  }, []);

  const confirm = React.useCallback(
    async (reason: string) => {
      if (!pending) return;
      const token = getAuthToken();
      if (!token) {
        setSubmitError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setSubmitError(null);
        const updated =
          pending.action === "hide"
            ? await hideAdminReview(token, reviewType, pending.review.id, reason)
            : await unhideAdminReview(token, reviewType, pending.review.id);
        onSuccess(updated);
        setPending(null);
      } catch (err) {
        setSubmitError(err instanceof AdminApiError ? err.message : "Failed to update the review.");
      }
    },
    [pending, reviewType, onSuccess]
  );

  return { pending, submitError, request, cancel, confirm };
}

/** Shown instead of the module when the operator lacks reviews.moderate. */
export function ReviewAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-accent/10 text-accent flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Your account does not hold the permission required to open{" "}
          <strong className="text-ink">Reviews</strong>. Review moderation requires{" "}
          <code className="font-mono text-[11px]">reviews.moderate</code>. Contact a Super
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
