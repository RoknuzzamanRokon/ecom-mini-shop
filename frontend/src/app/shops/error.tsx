"use client";

import { useEffect } from "react";
import StorefrontChrome from "@/components/layout/StorefrontChrome";
import Footer from "@/components/layout/Footer";
import { RouteErrorState } from "@/components/feedback";

export default function ShopsDirectoryError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Shops directory route error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <StorefrontChrome />
      <RouteErrorState
        title="Shops could not be loaded"
        description="Something went wrong while loading the shop directory. Please try again, or return to the catalog."
        icon="storefront"
        onRetry={reset}
        fallbackHref="/"
        fallbackLabel="Back to Store"
      />
      <Footer />
    </div>
  );
}
