"use client";

import { useEffect } from "react";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import { RouteErrorState } from "@/components/feedback";

/**
 * Separate from `not-found.tsx` on purpose: a missing product is a 404, whereas a
 * crash while rendering the detail view is an error the customer can retry.
 */
export default function ProductDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Product detail route error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <Header />
      <RouteErrorState
        title="This product could not be loaded"
        description="Something went wrong while loading this product. Please try again, or return to the catalog."
        icon="inventory_2"
        onRetry={reset}
        fallbackHref="/"
        fallbackLabel="Back to Store"
      />
      <Footer />
    </div>
  );
}
