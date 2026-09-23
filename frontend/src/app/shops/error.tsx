"use client";

import { useEffect } from "react";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
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
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>
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
