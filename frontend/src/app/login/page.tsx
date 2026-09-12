"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <>
          <div className="sticky top-0 z-40 w-full shadow-sm">
            <Header />
            <Navbar />
          </div>
          <main className="flex-1 flex items-center justify-center bg-page">
            <div className="flex items-center gap-2 text-ink-muted">
              <span className="material-symbols-outlined animate-spin text-[24px]">
                progress_activity
              </span>
              <span className="text-sm">Loading...</span>
            </div>
          </main>
        </>
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, isLoading: authLoading } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      const next = searchParams.get("next") || "/";
      router.replace(next);
    }
  }, [isAuthenticated, authLoading, router, searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Client-side validation
    if (!username.trim()) {
      setError("Username is required.");
      return;
    }
    if (!password) {
      setError("Password is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(username.trim(), password);
      const next = searchParams.get("next") || "/";
      router.replace(next);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Login failed. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Show nothing while checking auth state to avoid flash
  if (authLoading) {
    return (
      <>
        <div className="sticky top-0 z-40 w-full shadow-sm">
          <Header />
          <Navbar />
        </div>
        <main className="flex-1 flex items-center justify-center bg-page">
          <div className="flex items-center gap-2 text-ink-muted">
            <span className="material-symbols-outlined animate-spin text-[24px]">
              progress_activity
            </span>
            <span className="text-sm">Loading...</span>
          </div>
        </main>
      </>
    );
  }

  // Already authenticated — will redirect via useEffect
  if (isAuthenticated) {
    return null;
  }

  return (
    <>
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="flex-1 flex items-center justify-center bg-page px-4 py-12">
        <div className="w-full max-w-md">
          {/* Card */}
          <div className="bg-surface rounded-xl shadow-lg border border-line p-8">
            {/* Header */}
            <div className="text-center mb-8">
              <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="material-symbols-outlined text-[28px] text-accent">
                  lock
                </span>
              </div>
              <h1 className="text-2xl font-bold text-ink">Welcome Back</h1>
              <p className="text-sm text-ink-muted mt-1">
                Sign in to your MiniShop account
              </p>
            </div>

            {/* Error Alert */}
            {error && (
              <div className="mb-6 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
                <span className="material-symbols-outlined text-[18px] mt-0.5 shrink-0">
                  error
                </span>
                <span>{error}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Username */}
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-ink mb-1.5"
                >
                  Username
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    person
                  </span>
                  <input
                    id="username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your username"
                    autoComplete="username"
                    autoFocus
                    disabled={isSubmitting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-ink mb-1.5"
                >
                  Password
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    lock
                  </span>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    disabled={isSubmitting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-semibold text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[18px]">
                      progress_activity
                    </span>
                    Signing in...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[18px]">
                      login
                    </span>
                    Sign In
                  </>
                )}
              </button>
            </form>

            {/* Registration Link */}
            <div className="mt-6 pt-5 border-t border-line text-center">
              <p className="text-sm text-ink-muted">
                New to MiniShop?{" "}
                <Link
                  href={
                    searchParams.get("next")
                      ? `/register?next=${encodeURIComponent(searchParams.get("next")!)}`
                      : "/register"
                  }
                  className="font-semibold text-accent hover:underline"
                >
                  Create an account
                </Link>
              </p>
            </div>

            {/* Back to Store */}
            <div className="mt-4 text-center">
              <Link
                href="/"
                className="text-xs text-ink-muted hover:text-ink inline-flex items-center gap-1 transition-colors"
              >
                <span className="material-symbols-outlined text-[14px]">
                  arrow_back
                </span>
                Back to Store
              </Link>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
