import StorefrontChrome from "@/components/layout/StorefrontChrome";
import Footer from "@/components/layout/Footer";
import { RouteSpinner } from "@/components/feedback";

/** Mirrors the page's own loading branch so the two are indistinguishable. */
export default function ProductDetailLoading() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <StorefrontChrome />
      <RouteSpinner label="Loading product…" />
      <Footer />
    </div>
  );
}
