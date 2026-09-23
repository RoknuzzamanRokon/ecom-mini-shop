import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { RouteSpinner } from "@/components/feedback";

/**
 * Fallback for storefront segments that have no closer `loading.tsx`
 * (`/`, `/login`, `/register`, `/checkout`, `/order-success/[orderNumber]`).
 *
 * The chrome is rendered here as well as by the pages themselves so that the
 * hand-off from this fallback to the real page does not shift the layout — every
 * storefront page mounts its own sticky Header + Navbar pair.
 */
export default function StorefrontLoading() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>
      <RouteSpinner label="Loading page…" />
      <Footer />
    </div>
  );
}
