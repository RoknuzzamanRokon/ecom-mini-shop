"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  getProductReviews,
  getMyProductReview,
  createReview,
  updateReview,
  deleteReview,
} from "@/lib/api";
import { Review } from "@/lib/types";

interface ProductReviewsProps {
  productId: number;
  onReviewsChanged?: () => void;
}

function StarRow({ rating, size = 16 }: { rating: number; size?: number }) {
  const rounded = Math.round(rating);
  return (
    <div className="flex items-center text-star">
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          className="material-symbols-outlined"
          style={{
            fontSize: size,
            fontVariationSettings: n <= rounded ? "'FILL' 1" : "'FILL' 0",
          }}
        >
          star
        </span>
      ))}
    </div>
  );
}

function StarPicker({
  value,
  onChange,
}: {
  value: number;
  onChange: (rating: number) => void;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const active = hovered ?? value;

  return (
    <div className="flex items-center gap-0.5 text-star">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          onMouseEnter={() => setHovered(n)}
          onMouseLeave={() => setHovered(null)}
          className="cursor-pointer"
          aria-label={`${n} star${n === 1 ? "" : "s"}`}
        >
          <span
            className="material-symbols-outlined text-[22px]"
            style={{ fontVariationSettings: n <= active ? "'FILL' 1" : "'FILL' 0" }}
          >
            star
          </span>
        </button>
      ))}
    </div>
  );
}

export default function ProductReviews({ productId, onReviewsChanged }: ProductReviewsProps) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  const [reviews, setReviews] = useState<Review[]>([]);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [myReview, setMyReview] = useState<Review | null>(null);
  const [checkingMyReview, setCheckingMyReview] = useState(false);

  const [formRating, setFormRating] = useState(0);
  const [formComment, setFormComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const loadReviews = useCallback(
    async (targetPage: number) => {
      try {
        setLoading(true);
        setError(null);
        const res = await getProductReviews(productId, targetPage);
        setReviews(res.results);
        setTotalCount(res.count);
        setHasNext(Boolean(res.next));
        setPage(targetPage);
      } catch {
        setError("Could not load reviews.");
      } finally {
        setLoading(false);
      }
    },
    [productId]
  );

  const loadMyReview = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setMyReview(null);
      return;
    }
    try {
      setCheckingMyReview(true);
      const existing = await getMyProductReview(productId, token);
      setMyReview(existing);
      if (existing) {
        setFormRating(existing.rating);
        setFormComment(existing.comment);
      } else {
        setFormRating(0);
        setFormComment("");
      }
    } finally {
      setCheckingMyReview(false);
    }
  }, [productId]);

  useEffect(() => {
    loadReviews(1);
  }, [loadReviews]);

  useEffect(() => {
    if (isAuthenticated) {
      loadMyReview();
    } else {
      setMyReview(null);
    }
  }, [isAuthenticated, loadMyReview]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;
    if (formRating < 1) {
      setFormError("Please select a star rating.");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      if (myReview) {
        const updated = await updateReview(
          myReview.id,
          { rating: formRating, comment: formComment },
          token
        );
        setMyReview(updated);
      } else {
        const created = await createReview(
          { product_id: productId, rating: formRating, comment: formComment },
          token
        );
        setMyReview(created);
      }
      setEditing(false);
      await loadReviews(1);
      onReviewsChanged?.();
    } catch (err: any) {
      setFormError(err.message || "Failed to submit review.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    const token = getAuthToken();
    if (!token || !myReview) return;
    setSubmitting(true);
    try {
      await deleteReview(myReview.id, token);
      setMyReview(null);
      setFormRating(0);
      setFormComment("");
      setEditing(false);
      await loadReviews(1);
      onReviewsChanged?.();
    } catch {
      setFormError("Failed to delete review.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-12 bg-surface rounded-xl border border-line p-6 lg:p-8 shadow-sm">
      <h3 className="font-bold text-base uppercase tracking-wider text-ink mb-4">
        Customer Reviews {totalCount > 0 && `(${totalCount})`}
      </h3>

      {/* Submit / edit form */}
      {!isAuthenticated ? (
        <div className="p-3.5 rounded-lg bg-surface-alt/60 border border-line text-xs text-ink-muted flex items-center justify-between gap-3 mb-6">
          <span>Log in to write a review.</span>
          <button
            type="button"
            onClick={() => router.push("/login")}
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
              <StarRow rating={myReview.rating} />
              <span className="text-xs font-semibold text-ink-muted">Your review</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setEditing(true)}
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
            placeholder="Share your experience with this product (optional)..."
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
                  setFormRating(myReview.rating);
                  setFormComment(myReview.comment);
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

      {/* Review list */}
      {loading ? (
        <div className="py-8 text-center text-xs text-ink-muted">Loading reviews…</div>
      ) : error ? (
        <div className="py-8 text-center">
          <p className="text-xs text-accent font-semibold">{error}</p>
          <button
            type="button"
            onClick={() => loadReviews(1)}
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
                  <StarRow rating={review.rating} size={14} />
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
            onClick={() => loadReviews(page - 1)}
            className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer"
          >
            Previous
          </button>
          <span className="text-ink-muted">Page {page}</span>
          <button
            type="button"
            disabled={!hasNext}
            onClick={() => loadReviews(page + 1)}
            className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold cursor-pointer"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
