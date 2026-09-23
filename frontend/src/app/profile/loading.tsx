import { RouteSpinner } from "@/components/feedback";

/**
 * Rendered inside the profile layout, so the sidebar, header and route guard stay
 * mounted while the segment's code loads.
 */
export default function ProfileSectionLoading() {
  return <RouteSpinner label="Loading account…" />;
}
