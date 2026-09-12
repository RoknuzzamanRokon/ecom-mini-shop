"use client";

import React, { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Wraps children with an authentication guard.
 * If the user is not authenticated, redirects to /login?next=<current_path>.
 *
 * Usage (in a future /account/* page):
 *   <ProtectedRoute>
 *     <AccountDashboard />
 *   </ProtectedRoute>
 *
 * Note: This is a frontend convenience guard only.
 * Backend authorization remains the authoritative security boundary.
 */
export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const returnUrl = encodeURIComponent(pathname);
      router.replace(`/login?next=${returnUrl}`);
    }
  }, [isAuthenticated, isLoading, router, pathname]);

  // Show loading state while auth is being determined
  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-page min-h-[300px]">
        <div className="flex items-center gap-2 text-ink-muted">
          <span className="material-symbols-outlined animate-spin text-[24px]">
            progress_activity
          </span>
          <span className="text-sm">Checking authentication...</span>
        </div>
      </div>
    );
  }

  // Not authenticated — useEffect will redirect
  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
