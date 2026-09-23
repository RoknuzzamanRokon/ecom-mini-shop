import Link from "next/link";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";

/**
 * 404 for URLs that match no route at all.
 *
 * Note this never fires under `/admin`: `admin/[...slug]` is a catch-all that
 * renders a module placeholder for any unknown management path, so the admin
 * console deliberately has no 404 of its own.
 */
export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <span className="material-symbols-outlined text-[64px] text-ink-muted/50 mb-2">
          travel_explore
        </span>
        <h1 className="text-xl font-bold text-ink">Page Not Found</h1>
        <p className="text-sm text-ink-body mt-1 max-w-md">
          The page you are looking for does not exist, or it may have been moved.
        </p>
        <div className="mt-4 flex flex-col sm:flex-row gap-2">
          <Link
            href="/"
            className="bg-primary hover:bg-primary-hover text-on-primary px-4 py-2 rounded-md font-semibold text-xs uppercase shadow-xs transition-colors"
          >
            Back to Store
          </Link>
          <Link
            href="/shops"
            className="border border-line text-ink hover:bg-surface-alt px-4 py-2 rounded-md font-semibold text-xs uppercase transition-colors"
          >
            Browse Shops
          </Link>
        </div>
      </div>
      <Footer />
    </div>
  );
}
