"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import SellerAccountRequired from "@/components/seller/SellerAccountRequired";
import { getSellerDashboard, SellerProfileMissingError } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { SellerDashboardData, SellerProfile, SellerCapabilities } from "@/lib/types";

interface SellerContextType {
  dashboardData: SellerDashboardData | null;
  seller: SellerProfile | null;
  capabilities: SellerCapabilities | null;
  /** True only until the first dashboard load settles. */
  loading: boolean;
  /** A background refreshDashboard() is in flight; the page stays mounted. */
  refreshing: boolean;
  error: string | null;
  refreshDashboard: () => Promise<void>;
}

const SellerContext = createContext<SellerContextType | undefined>(undefined);

export function useSeller() {
  const context = useContext(SellerContext);
  if (!context) {
    throw new Error("useSeller must be used within a SellerGuard/SellerProvider");
  }
  return context;
}

export default function SellerGuard({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const [dashboardData, setDashboardData] = useState<SellerDashboardData | null>(null);
  // The first load shows the full-screen spinner; later refreshes only set
  // `refreshing`, so a page's own state (a success message) survives them
  // (BUG-072).
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isNotSeller, setIsNotSeller] = useState(false);

  // State changes only in the promise callbacks, so calling this from the
  // effect below never sets state synchronously.
  const fetchDashboard = useCallback((): Promise<void> => {
    const token = getAuthToken();
    if (!token) return Promise.resolve().then(() => setLoading(false));

    return getSellerDashboard(token)
      .then((data) => {
        setDashboardData(data);
        setIsNotSeller(false);
        setError(null);
      })
      .catch((err: unknown) => {
        if (err instanceof SellerProfileMissingError) {
          setIsNotSeller(true);
        } else {
          // Shown as an error with Retry, never as a "Not Operational" portal
          // built from missing data (BUG-030).
          setError(err instanceof Error && err.message ? err.message : "Failed to load seller information.");
        }
      })
      .finally(() => {
        setRefreshing(false);
        setLoading(false);
      });
  }, []);

  const refreshDashboard = useCallback(() => {
    setRefreshing(true);
    return fetchDashboard();
  }, [fetchDashboard]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchDashboard();
  }, [fetchDashboard]);

  useEffect(() => {
    if (authLoading) return;

    if (!isAuthenticated) {
      // replace, so Back does not return to a page that only redirects, and
      // keep the deep link for after sign-in.
      router.replace(`/login?next=${encodeURIComponent(pathname || "/seller")}`);
      return;
    }

    fetchDashboard();
  }, [isAuthenticated, authLoading, router, pathname, fetchDashboard]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-page">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
          <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
            Loading Seller Center...
          </p>
        </div>
      </div>
    );
  }

  // Not a registered seller
  if (isNotSeller) {
    return <SellerAccountRequired account={user?.email || user?.username} />;
  }

  if (error && !dashboardData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-page p-4">
        <div
          role="alert"
          className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center text-center gap-3"
        >
          <span className="material-symbols-outlined text-[40px] text-accent">cloud_off</span>
          <h1 className="text-lg font-black text-ink">Seller Center could not load</h1>
          <p className="text-xs text-ink-muted leading-relaxed">{error}</p>
          <button
            type="button"
            onClick={retry}
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold uppercase tracking-wider cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">refresh</span>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <SellerContext.Provider
      value={{
        dashboardData,
        seller: dashboardData?.seller || null,
        capabilities: dashboardData?.capabilities || null,
        loading,
        refreshing,
        error,
        refreshDashboard,
      }}
    >
      {children}
    </SellerContext.Provider>
  );
}
