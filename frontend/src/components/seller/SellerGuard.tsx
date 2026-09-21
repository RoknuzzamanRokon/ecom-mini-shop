"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getSellerDashboard } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { SellerDashboardData, SellerProfile, SellerCapabilities } from "@/lib/types";

interface SellerContextType {
  dashboardData: SellerDashboardData | null;
  seller: SellerProfile | null;
  capabilities: SellerCapabilities | null;
  loading: boolean;
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

  const [dashboardData, setDashboardData] = useState<SellerDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isNotSeller, setIsNotSeller] = useState(false);

  const fetchDashboard = useCallback(async () => {
    const token = getAuthToken();

    if (!token) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getSellerDashboard(token);
      setDashboardData(data);
      setIsNotSeller(false);
    } catch (err: any) {
      console.warn("Seller dashboard fetch error:", err);
      // 404 or missing seller profile
      if (
        err?.message?.includes("No seller profile") ||
        err?.message?.includes("404") ||
        err?.message?.includes("not have a seller")
      ) {
        setIsNotSeller(true);
      } else {
        setError(err?.message || "Failed to load seller information.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;

    if (!isAuthenticated) {
      router.push("/login?next=/seller");
      return;
    }

    fetchDashboard();
  }, [isAuthenticated, authLoading, router, fetchDashboard]);

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
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-page p-6 text-center">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-sm flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
            <span className="material-symbols-outlined text-[36px]">storefront</span>
          </div>
          <h1 className="text-xl font-extrabold text-ink tracking-tight mb-2">
            Seller Account Required
          </h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            The account <strong className="text-ink">{user?.email || user?.username}</strong> is not currently registered as a seller on MiniShop. To open your shop and sell products, please apply through platform administration.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 w-full">
            <Link
              href="/"
              className="flex-1 px-4 py-2.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-bold text-xs uppercase tracking-wider transition-colors"
            >
              Storefront
            </Link>
            <Link
              href="/profile"
              className="flex-1 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm"
            >
              Customer Profile
            </Link>
          </div>
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
        error,
        refreshDashboard: fetchDashboard,
      }}
    >
      {children}
    </SellerContext.Provider>
  );
}
