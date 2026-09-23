"use client";

import { useEffect } from "react";
import { RouteErrorState } from "@/components/feedback";

/**
 * Scoped to the admin section so the surrounding layout survives the failure —
 * Next renders this in place of the page only, keeping the layout's chrome and
 * guard intact. A failure in the layout itself bubbles to the root boundary.
 */
export default function AdminSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Admin section route error:", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center">
      <RouteErrorState
        title="This module could not be loaded"
        description="Something went wrong while loading this management module. Please try again, or return to the console overview."
        icon="admin_panel_settings"
        onRetry={reset}
        fallbackHref="/admin"
        fallbackLabel="Return to Overview"
      />
    </div>
  );
}
