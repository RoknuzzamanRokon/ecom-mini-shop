"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { loginUser, getCurrentUser } from "@/lib/api";
import { clearTokens, safeNextPath, setTokens } from "@/lib/auth";
import { isManagementUser } from "@/lib/admin-auth";
import LoginRing, {
  LoginRingPasswordField,
  SUCCESS_ANIMATION_MS,
  prefersReducedMotion,
  useLoginRingEffects,
} from "@/components/auth/LoginRing";

export default function AdminLoginPage() {
  return (
    <Suspense
      fallback={
        <AdminLoginShell>
          <div className="flex items-center gap-2 text-ink-muted">
            <span className="material-symbols-outlined animate-spin text-[24px]">
              progress_activity
            </span>
            <span className="text-sm">Loading console...</span>
          </div>
        </AdminLoginShell>
      }
    >
      <AdminLoginForm />
    </Suspense>
  );
}

/**
 * The console has no storefront chrome, so the sign-in ring gets a slim brand
 * bar in the navbar's colours instead of the storefront's search and links.
 * Text is --c-nav-text, not --c-on-primary, which is near-black in dark mode.
 */
function AdminLoginShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <header className="sticky top-0 z-40 w-full bg-nav shadow-sm">
        <div className="max-w-[1360px] mx-auto px-4 sm:px-6 py-2.5 flex items-center gap-3">
          <Link
            href="/"
            // The wordmark is dark navy, so the chip stays light in every theme
            // rather than following --c-surface into dark mode (as in Header).
            className="flex items-center bg-[#FBF9F4] px-3 py-1.5 rounded-lg shadow-sm border border-line/40 transition-transform active:scale-98"
          >
            <Image
              src="/logo.png"
              alt="MiniShop"
              width={440}
              height={149}
              priority
              className="h-8 w-auto"
            />
          </Link>
          <span className="h-6 w-px bg-nav-text/30" aria-hidden="true" />
          <span className="text-sm font-semibold tracking-wide text-nav-text">
            Admin console
          </span>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-10">
        {children}
      </main>
    </div>
  );
}

function AdminLoginForm() {
  const searchParams = useSearchParams();
  // AdminGuard sets ?redirect= to the page that bounced here, but anyone can
  // craft the link, so only a path on this site is followed.
  const redirectTo = safeNextPath(searchParams.get("redirect"), "/admin");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const { formRef, beadsRef, playErrorEffect } = useLoginRingEffects();
  const redirectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // A full page load rather than router.replace(), so AuthContext rehydrates
  // from the tokens just stored.
  const enterConsole = () => {
    window.location.href = redirectTo;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username.trim() || !password) {
      showError("Please enter your username and password.");
      return;
    }

    setIsSubmitting(true);
    try {
      // 1. Obtain JWT tokens
      const tokens = await loginUser(username.trim(), password);

      // 2. Fetch authenticated profile to verify management roles and permissions
      const userData = await getCurrentUser(tokens.access);

      // 3. Reject non-management users
      if (!isManagementUser(userData)) {
        // Purge tokens immediately, through the shared accessor (Phase 2J) so
        // the legacy access-token keys it also clears cannot leave a
        // non-management session half-signed-in.
        clearTokens();
        showError("Access denied: You do not have management portal permissions.");
        return;
      }

      // 4. Store tokens for session persistence, through the shared accessor
      //    (Phase 2J) rather than raw localStorage literals.
      setTokens(tokens.access, tokens.refresh);

      // 5. Sink the rings, then open the console at the preserved destination
      if (prefersReducedMotion()) {
        enterConsole();
      } else {
        setIsSuccess(true);
        redirectTimer.current = setTimeout(enterConsole, SUCCESS_ANIMATION_MS);
      }
    } catch (err) {
      console.error("Management login failed:", err);
      showError(
        err instanceof Error && err.message
          ? err.message
          : "Invalid credentials. Please verify your username and password."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AdminLoginShell>
      <LoginRing
        success={isSuccess}
        beadsRef={beadsRef}
        welcome={
          <>
            <h2>Welcome back</h2>
            <p>Opening the console…</p>
          </>
        }
      >
        <form ref={formRef} onSubmit={handleSubmit} className="login-ring__form">
          <h1 className="login-ring__title">Staff Sign In</h1>
          <p className="login-ring__subtitle">MiniShop management console</p>

          <div className="login-ring__field">
            <label htmlFor="username" className="login-ring__label">
              Username
            </label>
            <input
              id="username"
              name="username"
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
            name="password"
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

      {/* Access note + back link sit under the ring */}
      <div
        className={`mt-2 flex flex-col items-center gap-3 transition-opacity duration-300 ${
          isSuccess ? "opacity-0" : ""
        }`}
      >
        <p className="text-sm text-ink-muted inline-flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">lock</span>
          Authorized personnel only
        </p>
        <Link
          href="/"
          className="text-xs text-ink-muted hover:text-ink inline-flex items-center gap-1 transition-colors"
        >
          <span className="material-symbols-outlined text-[14px]">arrow_back</span>
          Back to Storefront
        </Link>
      </div>
    </AdminLoginShell>
  );
}
