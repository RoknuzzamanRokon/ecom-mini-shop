"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { registerCustomer } from "@/lib/api";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";

export default function RegisterPage() {
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
      <RegisterPageContent />
    </Suspense>
  );
}

function RegisterPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, isLoading: authLoading } = useAuth();

  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    password_confirm: "",
    first_name: "",
    last_name: "",
  });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nextDestination = searchParams.get("next") || "/";

  // Redirect if already authenticated
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      router.replace(nextDestination);
    }
  }, [isAuthenticated, authLoading, router, nextDestination]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Client-side validation
    const trimmedUsername = formData.username.trim();
    const trimmedEmail = formData.email.trim();

    if (!trimmedUsername) {
      setError("Username is required.");
      return;
    }
    if (!trimmedEmail) {
      setError("Email is required.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!formData.password) {
      setError("Password is required.");
      return;
    }
    if (formData.password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (formData.password !== formData.password_confirm) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      // 1. Call public registration endpoint
      await registerCustomer({
        username: trimmedUsername,
        email: trimmedEmail,
        password: formData.password,
        password_confirm: formData.password_confirm,
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
      });

      // 2. Seamlessly authenticate using the existing AuthContext
      await login(trimmedUsername, formData.password);

      // 3. Redirect to target destination (e.g. /checkout or /)
      router.replace(nextDestination);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Registration failed. Please verify your details."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Show loading skeleton while checking auth state
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

  // Already authenticated — redirecting via useEffect
  if (isAuthenticated) {
    return null;
  }

  const loginLink = searchParams.get("next")
    ? `/login?next=${encodeURIComponent(searchParams.get("next")!)}`
    : "/login";

  return (
    <>
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="flex-1 flex items-center justify-center bg-page px-4 py-10">
        <div className="w-full max-w-lg">
          {/* Registration Card */}
          <div className="bg-surface rounded-xl shadow-lg border border-line p-8">
            {/* Header */}
            <div className="text-center mb-6">
              <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="material-symbols-outlined text-[28px] text-accent">
                  person_add
                </span>
              </div>
              <h1 className="text-2xl font-bold text-ink">Create an Account</h1>
              <p className="text-sm text-ink-muted mt-1">
                Join MiniShop to enjoy fast checkout and order tracking
              </p>
            </div>

            {/* Error Alert */}
            {error && (
              <div className="mb-6 p-3.5 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
                <span className="material-symbols-outlined text-[18px] mt-0.5 shrink-0">
                  error
                </span>
                <span>{error}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Name Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="first_name"
                    className="block text-sm font-medium text-ink mb-1.5"
                  >
                    First Name
                  </label>
                  <input
                    id="first_name"
                    name="first_name"
                    type="text"
                    value={formData.first_name}
                    onChange={handleChange}
                    placeholder="e.g. John"
                    disabled={isSubmitting}
                    className="w-full px-3.5 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
                <div>
                  <label
                    htmlFor="last_name"
                    className="block text-sm font-medium text-ink mb-1.5"
                  >
                    Last Name
                  </label>
                  <input
                    id="last_name"
                    name="last_name"
                    type="text"
                    value={formData.last_name}
                    onChange={handleChange}
                    placeholder="e.g. Doe"
                    disabled={isSubmitting}
                    className="w-full px-3.5 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Username */}
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-ink mb-1.5"
                >
                  Username <span className="text-accent">*</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    account_circle
                  </span>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={formData.username}
                    onChange={handleChange}
                    placeholder="Choose a username"
                    autoComplete="username"
                    disabled={isSubmitting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Email */}
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-ink mb-1.5"
                >
                  Email Address <span className="text-accent">*</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    mail
                  </span>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    required
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="name@example.com"
                    autoComplete="email"
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
                  Password <span className="text-accent">*</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    lock
                  </span>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Minimum 8 characters"
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Password Confirm */}
              <div>
                <label
                  htmlFor="password_confirm"
                  className="block text-sm font-medium text-ink mb-1.5"
                >
                  Confirm Password <span className="text-accent">*</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-[20px] text-ink-muted">
                    lock_reset
                  </span>
                  <input
                    id="password_confirm"
                    name="password_confirm"
                    type="password"
                    required
                    value={formData.password_confirm}
                    onChange={handleChange}
                    placeholder="Re-enter password"
                    autoComplete="new-password"
                    disabled={isSubmitting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors"
                  />
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-semibold text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[18px]">
                      progress_activity
                    </span>
                    Creating Account...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[18px]">
                      check_circle
                    </span>
                    Create Account
                  </>
                )}
              </button>
            </form>

            {/* Login Link */}
            <div className="mt-6 pt-5 border-t border-line text-center">
              <p className="text-sm text-ink-muted">
                Already have an account?{" "}
                <Link
                  href={loginLink}
                  className="font-semibold text-accent hover:underline"
                >
                  Sign in
                </Link>
              </p>
            </div>

            {/* Back to store */}
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
