/**
 * The spinner every route-level `loading.tsx` renders.
 *
 * It intentionally reuses the exact markup the pages already use for their own
 * in-page loading branches (`animate-spin rounded-full h-10 w-10 border-b-2
 * border-primary`), so the hand-off from the route-segment fallback to a page's
 * own spinner is invisible rather than two different shapes in a row.
 */
export default function RouteSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className="flex-1 flex items-center justify-center py-24"
    >
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
