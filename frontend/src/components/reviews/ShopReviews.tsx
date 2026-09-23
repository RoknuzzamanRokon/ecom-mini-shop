"use client";

import React, { useMemo } from "react";
import {
  getShopReviews,
  getMyShopReview,
  createShopReview,
  updateShopReview,
  deleteShopReview,
} from "@/lib/api";
import { RatingBreakdown } from "@/lib/types";
import ReviewSection, { ReviewAdapter } from "@/components/reviews/ReviewSection";

/** DOM id of the shop page's review section, for "see reviews" links. */
export const SHOP_REVIEWS_ANCHOR = "shop-reviews";

interface ShopReviewsProps {
  shopId: number;
  /** The public list is addressed by slug; guests also return here after logging in. */
  shopSlug: string;
  /** Summary values from the shop detail payload. */
  averageRating?: number;
  reviewCount?: number;
  ratingBreakdown?: RatingBreakdown;
  onReviewsChanged?: () => void;
}

/** The shop page's review section: ReviewSection wired to the shop review API. */
export default function ShopReviews({
  shopId,
  shopSlug,
  averageRating,
  reviewCount,
  ratingBreakdown,
  onReviewsChanged,
}: ShopReviewsProps) {
  const adapter = useMemo<ReviewAdapter>(
    () => ({
      list: (page, ordering) => getShopReviews(shopSlug, page, ordering),
      getMine: (token) => getMyShopReview(shopId, token),
      create: (input, token) => createShopReview({ shop_id: shopId, ...input }, token),
      update: (reviewId, input, token) => updateShopReview(reviewId, input, token),
      remove: (reviewId, token) => deleteShopReview(reviewId, token),
    }),
    [shopId, shopSlug]
  );

  return (
    <ReviewSection
      key={shopId}
      id={SHOP_REVIEWS_ANCHOR}
      // Clears the sticky Header + Navbar when jumped to via #shop-reviews.
      className="scroll-mt-40"
      adapter={adapter}
      loginNext={`/shop/${shopSlug}`}
      commentPlaceholder="Share your experience with this shop (optional)..."
      averageRating={averageRating}
      reviewCount={reviewCount}
      ratingBreakdown={ratingBreakdown}
      onReviewsChanged={onReviewsChanged}
    />
  );
}
