import Link from "next/link";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";

/**
 * Rendered when the product page calls `notFound()` — i.e. no product exists for
 * the slug. Markup is carried over verbatim from the page's previous inline
 * "Product Not Found" branch so the customer-visible state is unchanged.
 */
export default function ProductNotFound() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <Header />
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <span className="material-symbols-outlined text-[64px] text-ink-muted/50 mb-2">
          inventory_2
        </span>
        <h2 className="text-xl font-bold text-ink">Product Not Found</h2>
        <p className="text-sm text-ink-body mt-1">The requested product could not be located.</p>
        <Link
          href="/"
          className="mt-4 bg-primary text-on-primary px-4 py-2 rounded-md font-semibold text-xs uppercase"
        >
          Back to Store
        </Link>
      </div>
      <Footer />
    </div>
  );
}
