"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { PaginatedResponse, RatingBreakdown, Review, ReviewOrdering } from "@/lib/types";
import RatingSummary from "@/components/reviews/RatingSummary";
import StarPicker from "@/components/reviews/StarPicker";
import StarRating from "@/components/reviews/StarRating";

export interface ReviewInput {
  rating: number;
  comment: string;
}

/**
 * The API calls behind one review section. Product and shop reviews share the
 * same UI and differ only here. Pass a memoized object (useMemo): a new adapter
 * reloads the list.
 */
export interface ReviewAdapter {
  list: (page: number, ordering: ReviewOrdering) => Promise<PaginatedResponse<Review>>;
  /** The caller's own review, or null when they haven't written one. */
  getMine: (token: string) => Promise<Review | null>;
  create: (input: ReviewInput, token: string) => Promise<Review>;
  update: (reviewId: number, input: ReviewInput, token: string) => Promise<Review>;
  remove: (reviewId: number, token: string) => Promise<void>;
}

interface ReviewSectionProps {
  adapter: ReviewAdapter;
  /** Path a guest returns to after logging in, e.g. "/product/some-slug". */
  loginNext: string;
  commentPlaceholder: string;
  /** Summary values from the reviewed product's or shop's detail payload. */
  averageRating?: number;
  reviewCount?: number;
  ratingBreakdown?: RatingBreakdown;
  onReviewsChanged?: () => void;
  /** DOM id for in-page links to this section. */
  id?: string;
  /** Extra classes for the outer card, e.g. a scroll margin under a sticky header. */
  className?: string;
}

const SORT_OPTIONS: { value: ReviewOrdering; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "highest", label: "Highest rated" },
  { value: "lowest", label: "Lowest rated" },
];

/**
 * Each fetch result is stored with the key of the request that produced it, so
 * "loading" is derived (stored key !== current key) instead of being set inside
 * an effect. The last good page is kept through errors so the heading count and
 * sort control don't flicker away.
 */
interface ListState {
  key: string;
  data?: PaginatedResponse<Review>;
  error?: string;
}

interface MineState {
  userId: number;
  review: Review | null;
}

/**
 * Review summary, write/edit form and paginated, sortable review list. Mount it
 * with a `key` per reviewed item so moving to another product or shop starts
 * from a clean state.
 */
export default function ReviewSection({
  adapter,
  loginNext,
  commentPlaceholder,
  averageRating = 0,
  reviewCount = 0,
  ratingBreakdown,
  onReviewsChanged,
  id,
  className = "",
}: ReviewSectionProps) {
  const { user, isAuthenticated } = useAuth();
  const router = useRouter();

  const [ordering, setOrdering] = useState<ReviewOrdering>("newest");
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);
  const [list, setList] = useState<ListState | null>(null);

  const [mine, setMine] = useState<MineState | null>(null);

  const [formRating, setFormRating] = useState(0);
  const [formComment, setFormComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const listKey = `${page}|${ordering}|${reloadToken}`;

  // Pages that load their data first (product, shop) render this section after
  // navigation has finished, so the browser never scrolled to a "#<id>" in the
  // URL. Do it once on mount.
  useEffect(() => {
    if (id && window.location.hash === `#${id}`) {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    adapter
      .list(page, ordering)
      .then((data) => {
        if (!cancelled) setList({ key: listKey, data });
      })
      .catch(() => {
        if (!cancelled) {
          setList((prev) => ({ key: listKey, data: prev?.data, error: "Could not load reviews." }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [adapter, page, ordering, listKey]);

  const userId = user?.id ?? null;
  useEffect(() => {
    if (userId === null) return;
    const token = getAuthToken();
    let cancelled = false;
    // A failed lookup (or a missing token) falls back to the create form; a
    // duplicate submit then gets the API's own "already reviewed" message.
    (token ? adapter.getMine(token).catch(() => null) : Promise.resolve(null)).then((review) => {
      if (!cancelled) setMine({ userId, review });
    });
    return () => {
      cancelled = true;
    };
  }, [adapter, userId]);

  const loading = list?.key !== listKey;
  const error = !loading ? list?.error ?? null : null;
  const reviews = list?.data?.results ?? [];
  const totalCount = list?.data?.count ?? 0;
  const hasNext = Boolean(list?.data?.next);

  const myReview = isAuthenticated && mine?.userId === userId ? mine.review : null;
  const checkingMyReview = isAuthenticated && mine?.userId !== userId;

  const reloadFirstPage = () => {
    setPage(1);
    setReloadToken((t) => t + 1);
  };

  const startEditing = (review: Review) => {
    setFormRating(review.rating);
    setFormComment(review.comment);
    setFormError(null);
    setEditing(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token || userId === null) return;
    if (formRating < 1) {
      setFormError("Please select a star rating.");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      const input = { rating: formRating, comment: formComment };
      const saved = myReview
        ? await adapter.update(myReview.id, input, token)
        : await adapter.create(input, token);
      setMine({ userId, review: saved });
      setEditing(false);
      reloadFirstPage();
      onReviewsChanged?.();
    } catch (err) {
      setFormError(err instanceof Error && err.message ? err.message : "Failed to submit review.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    const token = getAuthToken();
    if (!token || !myReview || userId === null) return;
    setSubmitting(true);
    try {
      await adapter.remove(myReview.id, token);
      setMine({ userId, review: null });
      setFormRating(0);
      setFormComment("");
      setEditing(false);
      reloadFirstPage();
      onReviewsChanged?.();
    } catch {
      setFormError("Failed to delete review.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      id={id}
      className={`mt-12 bg-surface rounded-xl border border-line p-6 lg:p-8 shadow-sm ${className}`}
    >
      <h3 className="font-bold text-base uppercase tracking-wider text-ink mb-4">
        Customer Reviews {totalCount > 0 && `(${totalCount})`}
      </h3>

      {reviewCount > 0 && (
        <div className="pb-6 mb-6 border-b border-line">
          <RatingSummary average={averageRating} count={reviewCount} breakdown={ratingBreakdown} />
        </div>
      )}

      {/* Submit / edit form */}
      {!isAuthenticated ? (
        <div className="p-3.5 rounded-lg bg-surface-alt/60 border border-line text-xs text-ink-muted flex items-center justify-between gap-3 mb-6">
          <span>Log in to write a review.</span>
          <button
            type="button"
            onClick={() => router.push(`/login?next=${encodeURIComponent(loginNext)}`)}
            className="shrink-0 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Log In
          </button>
        </div>
      ) : checkingMyReview ? (
        <div className="mb-6 text-xs text-ink-muted">Checking your review status…</div>
      ) : myReview && !editing ? (
        <div className="p-4 rounded-lg bg-surface-alt/40 border border-line mb-6">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <StarRating rating={myReview.rating} size={16} />
              <span className="text-xs font-semibold text-ink-muted">Your review</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => startEditing(myReview)}
                className="text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={submitting}
                className="text-xs font-bold uppercase tracking-wider text-accent hover:underline cursor-pointer disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
          {myReview.comment && (
            <p className="text-sm text-ink-body mt-2">{myReview.comment}</p>
          )}
        </div>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="p-4 rounded-lg bg-surface-alt/40 border border-line mb-6 space-y-3"
        >
          <p className="text-xs font-semibold text-ink">
            {myReview ? "Edit your review" : "Write a review"}
          </p>
          <StarPicker value={formRating} onChange={setFormRating} />
          <textarea
            rows={3}
            value={formComment}
            onChange={(e) => setFormComment(e.target.value)}
            placeholder={commentPlaceholder}
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          />
          {formError && <p className="text-xs text-accent font-semibold">{formError}</p>}
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              {submitting ? "Saving..." : myReview ? "Save Changes" : "Submit Review"}
            </button>
            {myReview && editing && (
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setFormError(null);
                }}
                className="text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink cursor-pointer"
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      {/* Sort control: only useful once there is more than one review */}
      {totalCount > 1 && (
        <div className="flex items-center justify-end mb-3">
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            <span>Sort by</span>
            <select
              value={ordering}
              onChange={(e) => {
                setOrdering(e.target.value as ReviewOrdering);
                setPage(1);
              }}
              className="bg-surface-alt border border-line rounded-lg px-3 py-2 text-xs font-medium text-ink focus:outline-hidden focus:border-primary cursor-pointer"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {/* Review list */}
      {loading ? (
        <div className="py-8 text-center text-xs text-ink-muted">Loading reviews…</div>
      ) : error ? (
        <div className="py-8 text-center">
          <p className="text-xs text-accent font-semibold">{error}</p>
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="mt-2 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : reviews.length === 0 ? (
        <div className="py-8 text-center text-xs text-ink-muted">
          No reviews yet. Be the first to share your thoughts.
        </div>
      ) : (
        <div className="divide-y divide-line">
          {reviews.map((review) => (
            <div key={review.id} className="py-4 first:pt-0">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <StarRating rating={review.rating} size={14} />
                  <span className="text-xs font-bold text-ink">{review.reviewer_name}</span>
                  {review.is_verified_purchase && (
                    <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-success/10 text-success border border-success/30 uppercase">
                      Verified Purchase
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-ink-muted">
                  {new Date(review.created_at).toLocaleDateString()}
                </span>
              </div>
              {review.comment && (
                <p className="text-sm text-ink-body mt-1.5">{review.comment}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {(page > 1 || hasNext) && !loading && !error && (
        <div className="flex items-center justify-between pt-4 mt-2 border-t border-line text-xs">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer"
          >
            Previous
          </button>
          <span className="text-ink-muted">Page {page}</span>
          <button
            type="button"
            disabled={!hasNext}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
