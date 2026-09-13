"use client";

import React, { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { loginUser, getCurrentUser } from "@/lib/api";
import { isManagementUser } from "@/lib/admin-auth";

export default function AdminLoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
            <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
              Loading Console...
            </p>
          </div>
        </div>
      }
    >
      <AdminLoginForm />
    </Suspense>
  );
}

function AdminLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectParam = searchParams.get("redirect") || "/admin";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError("Please enter your username and password.");
      return;
    }

    setLoading(true);

    try {
      // 1. Obtain JWT tokens
      const tokens = await loginUser(username.trim(), password);

      // 2. Fetch authenticated profile to verify management roles and permissions
      const userData = await getCurrentUser(tokens.access);

      // 3. Reject non-management users
      if (!isManagementUser(userData)) {
        // Purge tokens immediately
        if (typeof window !== "undefined") {
          localStorage.removeItem("minishop_token");
          localStorage.removeItem("minishop_refresh_token");
        }
        setError("Access denied: You do not have management portal permissions.");
        setLoading(false);
        return;
      }

      // 4. Store tokens in local storage for session persistence
      if (typeof window !== "undefined") {
        localStorage.setItem("minishop_token", tokens.access);
        localStorage.setItem("minishop_refresh_token", tokens.refresh);
      }

      // 5. Redirect to management dashboard or preserved destination
      // Using window.location.href to ensure full AuthContext state rehydration on navigation
      window.location.href = redirectParam;
    } catch (err: any) {
      console.error("Management login failed:", err);
      setError(
        err?.message || "Invalid credentials. Please verify your username and password."
      );
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-page">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        {/* Management Portal Badge */}
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-on-primary shadow-lg shadow-primary/20 mb-4">
          <span className="material-symbols-outlined text-[36px]">admin_panel_settings</span>
        </div>
        <h2 className="text-2xl font-black text-ink tracking-tight">
          MiniShop Management
        </h2>
        <p className="mt-1 text-xs uppercase font-bold tracking-widest text-ink-muted">
          Staff & Operations Portal
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md px-4">
        <div className="bg-surface py-8 px-6 sm:px-10 rounded-2xl border border-line shadow-sm">
          {error && (
            <div className="mb-6 p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 text-xs flex items-start gap-2.5">
              <span className="material-symbols-outlined text-[18px] shrink-0 mt-0.5">
                error
              </span>
              <span className="font-medium leading-relaxed">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-xs font-bold uppercase tracking-wider text-ink mb-1.5"
              >
                Staff Username / Email
              </label>
              <div className="relative">
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin or staff@minishop.com"
                  className="w-full px-3.5 py-2.5 bg-surface-alt border border-line rounded-xl text-xs text-ink placeholder:text-ink-muted focus:outline-hidden focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-bold uppercase tracking-wider text-ink mb-1.5"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full px-3.5 py-2.5 bg-surface-alt border border-line rounded-xl text-xs text-ink placeholder:text-ink-muted focus:outline-hidden focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <>
                    <div className="h-4 w-4 border-2 border-on-primary border-t-transparent rounded-full animate-spin" />
                    <span>Verifying Credentials...</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[18px]">login</span>
                    <span>Sign In to Console</span>
                  </>
                )}
              </button>
            </div>
          </form>

          <div className="mt-6 pt-6 border-t border-line flex items-center justify-between text-xs text-ink-muted">
            <Link
              href="/"
              className="hover:text-ink transition-colors flex items-center gap-1 font-medium"
            >
              <span className="material-symbols-outlined text-[14px]">arrow_back</span>
              <span>Back to Storefront</span>
            </Link>
            <span className="text-[10px] text-ink-muted">Authorized Personnel Only</span>
          </div>
        </div>
      </div>
    </div>
  );
}
