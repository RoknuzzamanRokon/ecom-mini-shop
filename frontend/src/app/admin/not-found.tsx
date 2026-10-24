import Link from "next/link";

/**
 * The Console's 404, for addresses under /admin that match no page (see
 * admin/[...slug]). Rendered inside the Console layout, so the sidebar and
 * header stay.
 */
export default function AdminNotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            travel_explore
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">Page not found</h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          There is no Console page at this address. It may be mistyped, or the link that brought
          you here is out of date.
        </p>
        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}
