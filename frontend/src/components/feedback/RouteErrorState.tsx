"use client";

import Link from "next/link";

export interface RouteErrorStateProps {
  /** Short heading naming what failed, in the storefront's own terms. */
  title?: string;
  /** One line telling the customer the content could not be loaded. */
  description?: string;
  /** Material symbol drawn in the status disc. */
  icon?: string;
  /**
   * The segment's `reset()`. Re-rendering the segment remounts the page, which
   * re-runs its effects and therefore its fetches — the retry is the framework's,
   * not a second copy of the page's data-loading code.
   */
  onRetry: () => void;
  /** Somewhere safe to go when retrying keeps failing. */
  fallbackHref?: string;
  fallbackLabel?: string;
}

/**
 * The shared body of every route-level `error.tsx`.
 *
 * Deliberately says nothing about *why* it failed: `error.message` on a
 * production build is a redacted digest, and on a dev build it is a stack-adjacent
 * internal string. Neither belongs in front of a customer, so the boundaries log
 * the real error to the console and show this instead.
 */
export default function RouteErrorState({
  title = "Something went wrong",
  description = "We could not load this content. This is usually temporary — please try again.",
  icon = "error",
  onRetry,
  fallbackHref = "/",
  fallbackLabel = "Back to Store",
}: RouteErrorStateProps) {
  return (
    <div className="w-full flex-1 flex items-center justify-center p-6">
      <div
        role="alert"
        className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-danger/10 text-danger flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            {icon}
          </span>
        </div>

        <h1 className="text-xl font-black text-ink tracking-tight mb-2">{title}</h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">{description}</p>

        <div className="w-full flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              refresh
            </span>
            Try Again
          </button>
          <Link
            href={fallbackHref}
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-xl border border-line text-ink hover:bg-surface-alt font-bold text-xs uppercase tracking-wider transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {fallbackLabel}
          </Link>
        </div>
      </div>
    </div>
  );
}
