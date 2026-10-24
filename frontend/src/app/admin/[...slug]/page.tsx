import { notFound } from "next/navigation";

/**
 * Any /admin/... address no Console route matches: a typo, a stale link, or
 * a path nested under a real page (/admin/users/5/edit). Every navigation
 * item has its own page now, so this is a 404, shown by admin/not-found.tsx
 * inside the Console layout (BUG-082).
 */
export default function AdminUnknownPage() {
  notFound();
}
