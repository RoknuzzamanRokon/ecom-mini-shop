"use client";

import React, { useMemo } from "react";
import {
  getProductReviews,
  getMyProductReview,
  createReview,
  updateReview,
  deleteReview,
} from "@/lib/api";
import { RatingBreakdown } from "@/lib/types";
import ReviewSection, { ReviewAdapter } from "@/components/reviews/ReviewSection";

/** DOM id of the product page's review section, e.g. `/product/<slug>#reviews`. */
export const PRODUCT_REVIEWS_ANCHOR = "reviews";

interface ProductReviewsProps {
  productId: number;
  /** Used to bring a guest back to this product after logging in. */
  productSlug: string;
  /** Summary values from the product detail payload. */
  averageRating?: number;
  reviewCount?: number;
  ratingBreakdown?: RatingBreakdown;
  onReviewsChanged?: () => void;
}

/** The product page's review section: ReviewSection wired to the product review API. */
export default function ProductReviews({
  productId,
  productSlug,
  averageRating,
  reviewCount,
  ratingBreakdown,
  onReviewsChanged,
}: ProductReviewsProps) {
  const adapter = useMemo<ReviewAdapter>(
    () => ({
      list: (page, ordering) => getProductReviews(productId, page, ordering),
      getMine: (token) => getMyProductReview(productId, token),
      create: (input, token) => createReview({ product_id: productId, ...input }, token),
      update: (reviewId, input, token) => updateReview(reviewId, input, token),
      remove: (reviewId, token) => deleteReview(reviewId, token),
    }),
    [productId]
  );

  return (
    <ReviewSection
      key={productId}
      id={PRODUCT_REVIEWS_ANCHOR}
      // Clears the sticky Header + Navbar when jumped to via #reviews.
      className="scroll-mt-40"
      adapter={adapter}
      loginNext={`/product/${productSlug}`}
      commentPlaceholder="Share your experience with this product (optional)..."
      averageRating={averageRating}
      reviewCount={reviewCount}
      ratingBreakdown={ratingBreakdown}
      onReviewsChanged={onReviewsChanged}
    />
  );
}
