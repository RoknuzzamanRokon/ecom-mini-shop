import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { RouteSpinner } from "@/components/feedback";

export default function ShopsDirectoryLoading() {
  return (
    <div className="min-h-screen flex flex-col bg-page">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>
      <RouteSpinner label="Loading shops…" />
      <Footer />
    </div>
  );
}
