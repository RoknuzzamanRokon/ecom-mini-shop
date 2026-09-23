import Link from "next/link";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";

/**
 * Rendered when the shop page calls `notFound()` — no shop is published under the
 * slug. Markup is carried over verbatim from the page's previous inline
 * "Shop Not Found" branch, including its note about inactive storefronts.
 */
export default function ShopNotFound() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <Header />
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <span className="material-symbols-outlined text-[64px] text-ink-muted/50 mb-2">
          store
        </span>
        <h2 className="text-xl font-bold text-ink">Shop Not Found</h2>
        <p className="text-sm text-ink-body mt-1">
          The requested shop storefront could not be located or is not currently active.
        </p>
        <Link
          href="/"
          className="mt-4 bg-primary text-on-primary px-4 py-2 rounded-md font-semibold text-xs uppercase shadow-xs hover:bg-primary-hover transition-colors"
        >
          Back to Catalog
        </Link>
      </div>
      <Footer />
    </div>
  );
}
