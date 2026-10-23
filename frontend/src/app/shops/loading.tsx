import StorefrontChrome from "@/components/layout/StorefrontChrome";
import Footer from "@/components/layout/Footer";
import { RouteSpinner } from "@/components/feedback";

export default function ShopsDirectoryLoading() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <StorefrontChrome />
      <RouteSpinner label="Loading shops…" />
      <Footer />
    </div>
  );
}
