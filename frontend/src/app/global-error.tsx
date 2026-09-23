"use client";

import { useEffect } from "react";
import "./globals.css";

/**
 * Last-resort boundary: the only one that can catch a failure in the root layout
 * itself (the theme/auth/profile/favorites/cart providers).
 *
 * It replaces the root layout, so it has to supply its own `<html>`/`<body>` and
 * import the stylesheet. The anti-flash script in the root layout does not run
 * here either, so no `data-theme` is set and the token defaults on `:root` apply —
 * which is why this still renders in the storefront's colours rather than raw HTML.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Fatal application error:", error);
  }, [error]);

  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen flex flex-col antialiased" suppressHydrationWarning>
        <div className="min-h-screen flex items-center justify-center bg-page p-6">
          <div
            role="alert"
            className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center text-center"
          >
            <div className="w-14 h-14 rounded-2xl bg-danger/10 text-danger flex items-center justify-center mb-4">
              <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
                error
              </span>
            </div>
            <h1 className="text-xl font-black text-ink tracking-tight mb-2">
              MiniShop could not start
            </h1>
            <p className="text-xs text-ink-muted leading-relaxed mb-6">
              An unexpected problem stopped the application from loading. Please try
              again — if it keeps happening, reload the browser tab.
            </p>
            <button
              type="button"
              onClick={reset}
              className="w-full inline-flex items-center justify-center gap-1.5 py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
