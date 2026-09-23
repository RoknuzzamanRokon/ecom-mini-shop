"use client";

import { useEffect } from "react";
import { RouteErrorState } from "@/components/feedback";

/**
 * Scoped to the profile section so the surrounding layout survives the failure —
 * Next renders this in place of the page only, keeping the layout's chrome and
 * guard intact. A failure in the layout itself bubbles to the root boundary.
 */
export default function ProfileSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Profile section route error:", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center">
      <RouteErrorState
        title="This page could not be loaded"
        description="Something went wrong while loading your account. Please try again, or return to your account overview."
        icon="account_circle"
        onRetry={reset}
        fallbackHref="/profile"
        fallbackLabel="Back to Account"
      />
    </div>
  );
}
