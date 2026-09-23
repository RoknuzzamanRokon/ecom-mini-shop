"use client";

import { useEffect } from "react";
import { RouteErrorState } from "@/components/feedback";

/**
 * Scoped to the seller section so the surrounding layout survives the failure —
 * Next renders this in place of the page only, keeping the layout's chrome and
 * guard intact. A failure in the layout itself bubbles to the root boundary.
 */
export default function SellerSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Seller section route error:", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center">
      <RouteErrorState
        title="This page could not be loaded"
        description="Something went wrong while loading your seller portal. Please try again, or return to your dashboard."
        icon="storefront"
        onRetry={reset}
        fallbackHref="/seller"
        fallbackLabel="Back to Dashboard"
      />
    </div>
  );
}
