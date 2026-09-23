"use client";

import { useEffect } from "react";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import { RouteErrorState } from "@/components/feedback";

/**
 * A shop that does not exist is a 404 (`not-found.tsx`); a crash while rendering
 * an existing shop's storefront is a retryable error and lands here.
 */
export default function ShopStorefrontError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Shop storefront route error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <Header />
      <RouteErrorState
        title="This shop could not be loaded"
        description="Something went wrong while loading this storefront. Please try again, or browse the other shops."
        icon="store"
        onRetry={reset}
        fallbackHref="/shops"
        fallbackLabel="Browse Shops"
      />
      <Footer />
    </div>
  );
}
