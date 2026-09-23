"use client";

import { useEffect } from "react";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { RouteErrorState } from "@/components/feedback";

/**
 * Storefront-wide error boundary.
 *
 * Catches render-phase failures in any segment that has no closer `error.tsx`,
 * plus failures in the `/admin`, `/seller` and `/profile` *layouts* — a segment's
 * own boundary cannot catch its own layout, so those bubble up to here.
 *
 * If the crash is in the chrome itself this boundary will throw while rendering
 * it, and Next escalates to `global-error.tsx`. That is the intended backstop:
 * the common case keeps the storefront frame, the rare case still gets a page.
 */
export default function StorefrontError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Storefront route error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>
      <RouteErrorState
        title="This page could not be loaded"
        description="Something went wrong while preparing this page. This is usually temporary — try again, or head back to the catalog."
        onRetry={reset}
        fallbackHref="/"
        fallbackLabel="Back to Store"
      />
      <Footer />
    </div>
  );
}
