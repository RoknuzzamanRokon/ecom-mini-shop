"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { safeNextPath } from "@/lib/auth";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import LoginRing, {
  LoginRingPasswordField,
  SUCCESS_ANIMATION_MS,
  prefersReducedMotion,
  useLoginRingEffects,
} from "@/components/auth/LoginRing";

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
  const [isSuccess, setIsSuccess] = useState(false);

  const { formRef, beadsRef, playErrorEffect } = useLoginRingEffects();
  const redirectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // `login()` flips isAuthenticated before it resolves. Holding off while a
  // submit is in flight or the success animation plays keeps this page on
  // screen long enough for the rings to sink in; handleSubmit redirects.
  const holdForAnimation = isSubmitting || isSuccess;

  // Redirect if already authenticated
  useEffect(() => {
    if (!authLoading && isAuthenticated && !holdForAnimation) {
      const next = safeNextPath(searchParams.get("next"));
      router.replace(next);
    }
  }, [isAuthenticated, authLoading, holdForAnimation, router, searchParams]);

  useEffect(
    () => () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current);
    },
    []
  );

  const showError = (message: string) => {
    setError(message);
    playErrorEffect();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Client-side validation
    if (!username.trim()) {
      showError("Username is required.");
      return;
    }
    if (!password) {
      showError("Password is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(username.trim(), password);
      const next = safeNextPath(searchParams.get("next"));
      if (prefersReducedMotion()) {
        router.replace(next);
      } else {
        setIsSuccess(true);
        redirectTimer.current = setTimeout(
          () => router.replace(next),
          SUCCESS_ANIMATION_MS
        );
      }
    } catch (err) {
      showError(
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
  if (isAuthenticated && !holdForAnimation) {
    return null;
  }

  return (
    <>
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="flex-1 flex flex-col items-center justify-center bg-page px-4 py-10">
        <LoginRing
          success={isSuccess}
          beadsRef={beadsRef}
          welcome={
            <>
              <h2>Welcome back</h2>
              <p>Signing you in…</p>
            </>
          }
        >
          <form
            ref={formRef}
            onSubmit={handleSubmit}
            className="login-ring__form"
          >
            <h1 className="login-ring__title">Welcome Back</h1>
            <p className="login-ring__subtitle">
              Sign in to your MiniShop account
            </p>

            <div className="login-ring__field">
              <label htmlFor="username" className="login-ring__label">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                autoFocus
                disabled={isSubmitting || isSuccess}
                className="login-ring__input"
              />
            </div>

            <LoginRingPasswordField
              value={password}
              onChange={setPassword}
              disabled={isSubmitting || isSuccess}
            />

            <div className="login-ring__error" role="alert">
              {error}
            </div>

            <button
              type="submit"
              disabled={isSubmitting || isSuccess}
              className="login-ring__submit"
            >
              {isSubmitting ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-[16px]">
                    progress_activity
                  </span>
                  Signing in...
                </>
              ) : (
                "Sign In"
              )}
            </button>
          </form>
        </LoginRing>

        {/* Registration + back links sit under the ring */}
        <div
          className={`mt-2 flex flex-col items-center gap-3 transition-opacity duration-300 ${
            isSuccess ? "opacity-0" : ""
          }`}
        >
          <p className="text-sm text-ink-muted">
            New to MiniShop?{" "}
            <Link
              href={
                searchParams.get("next")
                  ? `/register?next=${encodeURIComponent(searchParams.get("next")!)}`
                  : "/register"
              }
              className="font-semibold text-primary hover:underline"
            >
              Create an account
            </Link>
          </p>
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
      </main>
    </>
  );
}
