import { RouteSpinner } from "@/components/feedback";

/**
 * Rendered inside the admin layout, so the sidebar, header and route guard stay
 * mounted while the segment's code loads.
 */
export default function AdminSectionLoading() {
  return <RouteSpinner label="Loading module…" />;
}
