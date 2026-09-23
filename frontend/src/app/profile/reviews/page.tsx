"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { getAuthToken } from "@/lib/auth";
import {
  deleteReview,
  deleteShopReview,
  formatImageUrl,
  getMyReviews,
  updateReview,
  updateShopReview,
} from "@/lib/api";
import { MyReviews, Review } from "@/lib/types";
import { PRODUCT_REVIEWS_ANCHOR } from "@/components/product/ProductReviews";
import { ReviewInput } from "@/components/reviews/ReviewSection";
import { SHOP_REVIEWS_ANCHOR } from "@/components/reviews/ShopReviews";
import StarPicker from "@/components/reviews/StarPicker";
import StarRating from "@/components/reviews/StarRating";

type Tab = "products" | "shops";

/** The fetched reviews, stored with the reload token that produced them. */
interface LoadState {
  key: number;
  data?: MyReviews;
  error?: string;
}

export default function MyReviewsPage() {
  const [tab, setTab] = useState<Tab>("products");
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<LoadState | null>(null);

  useEffect(() => {
    let cancelled = false;
    const token = getAuthToken();
    (token ? getMyReviews(token) : Promise.reject(new Error("Not logged in")))
      .then((data) => {
        if (!cancelled) setState({ key: reloadToken, data });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ key: reloadToken, error: "We could not load your reviews. Please try again." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const loading = state?.key !== reloadToken;
  const data = loading ? undefined : state?.data;
  const error = loading ? undefined : state?.error;

  // Edits and deletes patch the loaded lists in place; no refetch needed.
  const patchData = (update: (current: MyReviews) => MyReviews) =>
    setState((prev) => (prev?.data ? { ...prev, data: update(prev.data) } : prev));

  const saveProductReview = async (id: number, input: ReviewInput) => {
    const token = getAuthToken();
    if (!token) throw new Error("Please log in again.");
    const updated = await updateReview(id, input, token);
    patchData((d) => ({
      ...d,
      product_reviews: d.product_reviews.map((r) => (r.id === id ? { ...r, ...updated } : r)),
    }));
  };

  const deleteProductReview = async (id: number) => {
    const token = getAuthToken();
    if (!token) throw new Error("Please log in again.");
    await deleteReview(id, token);
    patchData((d) => ({ ...d, product_reviews: d.product_reviews.filter((r) => r.id !== id) }));
  };

  const saveShopReview = async (id: number, input: ReviewInput) => {
    const token = getAuthToken();
    if (!token) throw new Error("Please log in again.");
    const updated = await updateShopReview(id, input, token);
    patchData((d) => ({
      ...d,
      shop_reviews: d.shop_reviews.map((r) => (r.id === id ? { ...r, ...updated } : r)),
    }));
  };

  const removeShopReview = async (id: number) => {
    const token = getAuthToken();
    if (!token) throw new Error("Please log in again.");
    await deleteShopReview(id, token);
    patchData((d) => ({ ...d, shop_reviews: d.shop_reviews.filter((r) => r.id !== id) }));
  };

  const productCount = data?.product_reviews.length ?? 0;
  const shopCount = data?.shop_reviews.length ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-bold text-ink">My Reviews</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Ratings and comments you have written for products and shops.
        </p>
      </div>

      <div role="tablist" aria-label="Review type" className="flex gap-2">
        {(
          [
            { value: "products", label: "Products", count: productCount },
            { value: "shops", label: "Shops", count: shopCount },
          ] as const
        ).map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={tab === option.value}
            onClick={() => setTab(option.value)}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors cursor-pointer ${
              tab === option.value
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface text-ink border-line hover:bg-surface-alt"
            }`}
          >
            {option.label}
            {data && ` (${option.count})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            reviews
          </span>
          <p className="text-sm text-ink-body mt-2">Loading your reviews…</p>
        </div>
      ) : error || !data ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center">
          <p className="text-sm text-accent font-medium">{error}</p>
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : tab === "products" ? (
        data.product_reviews.length === 0 ? (
          <EmptyState
            icon="inventory_2"
            title="No product reviews yet"
            body="Rate a product from its page and it will show up here."
            href="/"
            cta="Browse Products"
          />
        ) : (
          <div className="flex flex-col gap-3">
            {data.product_reviews.map((review) => (
              <MyReviewRow
                key={review.id}
                review={review}
                title={review.product.name}
                href={`/product/${review.product.slug}#${PRODUCT_REVIEWS_ANCHOR}`}
                imageUrl={review.product.image_url}
                fallbackIcon="inventory_2"
                onSave={(input) => saveProductReview(review.id, input)}
                onDelete={() => deleteProductReview(review.id)}
              />
            ))}
          </div>
        )
      ) : data.shop_reviews.length === 0 ? (
        <EmptyState
          icon="storefront"
          title="No shop reviews yet"
          body="Rate a shop from its page and it will show up here."
          href="/shops"
          cta="Browse Shops"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {data.shop_reviews.map((review) => (
            <MyReviewRow
              key={review.id}
              review={review}
              title={review.shop.name}
              href={`/shop/${review.shop.slug}#${SHOP_REVIEWS_ANCHOR}`}
              imageUrl={review.shop.logo_url}
              fallbackIcon="storefront"
              onSave={(input) => saveShopReview(review.id, input)}
              onDelete={() => removeShopReview(review.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState({
  icon,
  title,
  body,
  href,
  cta,
}: {
  icon: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="bg-surface rounded-2xl border border-line p-12 text-center">
      <span className="material-symbols-outlined text-[56px] text-ink-muted/40">{icon}</span>
      <h2 className="text-base font-bold text-ink mt-2">{title}</h2>
      <p className="text-sm text-ink-body mt-1 mb-5">{body}</p>
      <Link
        href={href}
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
      >
        {cta}
        <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
      </Link>
    </div>
  );
}

interface MyReviewRowProps {
  review: Review;
  title: string;
  /** Link to the review on its product or shop page. */
  href: string;
  imageUrl: string | null;
  fallbackIcon: string;
  onSave: (input: ReviewInput) => Promise<void>;
  onDelete: () => Promise<void>;
}

/** One of the user's reviews, with inline edit and delete. */
function MyReviewRow({ review, title, href, imageUrl, fallbackIcon, onSave, onDelete }: MyReviewRowProps) {
  const [editing, setEditing] = useState(false);
  const [rating, setRating] = useState(review.rating);
  const [comment, setComment] = useState(review.comment);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEditing = () => {
    setRating(review.rating);
    setComment(review.comment);
    setError(null);
    setEditing(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating < 1) {
      setError("Please select a star rating.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave({ rating, comment });
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Failed to save your review.");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    setError(null);
    try {
      // On success the row is removed from the list, so there is no state to reset.
      await onDelete();
    } catch {
      setError("Failed to delete review.");
      setBusy(false);
    }
  };

  return (
    <div className="bg-surface rounded-2xl border border-line shadow-sm p-4 flex items-start gap-4">
      <Link
        href={href}
        className="w-16 h-16 rounded-xl bg-surface-alt border border-line shrink-0 overflow-hidden relative flex items-center justify-center"
      >
        {imageUrl ? (
          <Image src={formatImageUrl(imageUrl)} alt={title} fill className="object-cover" />
        ) : (
          <span className="material-symbols-outlined text-[28px] text-ink-muted/50">{fallbackIcon}</span>
        )}
      </Link>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <Link
            href={href}
            className="text-sm font-bold text-ink hover:text-primary transition-colors line-clamp-1"
          >
            {title}
          </Link>
          <span className="text-[11px] text-ink-muted shrink-0">
            {new Date(review.created_at).toLocaleDateString()}
          </span>
        </div>

        {editing ? (
          <form onSubmit={handleSave} className="mt-2 space-y-3">
            <StarPicker value={rating} onChange={setRating} />
            <textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Share your experience (optional)..."
              className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
            />
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={busy}
                className="bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider px-4 py-2 rounded-lg shadow-sm transition-colors cursor-pointer"
              >
                {busy ? "Saving..." : "Save Changes"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setError(null);
                }}
                className="text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <div className="flex items-center gap-2 mt-1">
              <StarRating rating={review.rating} size={14} />
              {review.is_verified_purchase && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-success/10 text-success border border-success/30 uppercase">
                  Verified Purchase
                </span>
              )}
            </div>
            {review.comment && <p className="text-sm text-ink-body mt-1.5">{review.comment}</p>}
            <div className="flex items-center gap-3 mt-2">
              <button
                type="button"
                onClick={startEditing}
                className="text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="text-xs font-bold uppercase tracking-wider text-accent hover:underline cursor-pointer disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </>
        )}

        {error && <p className="text-xs text-accent font-semibold mt-2">{error}</p>}
      </div>
    </div>
  );
}
