import { RouteSpinner } from "@/components/feedback";

/**
 * Rendered inside the seller layout, so the sidebar, header and route guard stay
 * mounted while the segment's code loads.
 */
export default function SellerSectionLoading() {
  return <RouteSpinner label="Loading portal…" />;
}
