"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { isManagementUser, getManagementRoleLabel } from "@/lib/admin-auth";

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      const redirectUrl = pathname ? `/admin/login?redirect=${encodeURIComponent(pathname)}` : "/admin/login";
      router.push(redirectUrl);
    }
  }, [isAuthenticated, isLoading, router, pathname]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-page">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
          <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
            Loading Management Portal...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  // Check management eligibility
  if (!isManagementUser(user)) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-page p-6 text-center">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-sm flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center mb-4">
            <span className="material-symbols-outlined text-[36px]">shield_lock</span>
          </div>
          <h1 className="text-xl font-extrabold text-ink tracking-tight mb-2">
            Access Denied
          </h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            Access denied: You do not have management portal permissions. The account{" "}
            <strong className="text-ink">{user?.email || user?.username}</strong> is not authorized to view platform management resources.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 w-full">
            <Link
              href="/"
              className="flex-1 px-4 py-2.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-bold text-xs uppercase tracking-wider transition-colors"
            >
              Storefront
            </Link>
            <button
              type="button"
              onClick={() => {
                logout();
                router.push("/admin/login");
              }}
              className="flex-1 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm cursor-pointer"
            >
              Switch Account
            </button>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
