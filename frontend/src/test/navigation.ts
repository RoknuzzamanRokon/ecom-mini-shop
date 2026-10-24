/**
 * A stand-in for next/navigation's App Router hooks in component tests:
 *
 *   vi.mock("next/navigation", () => import("@/test/navigation"));
 *
 * router.replace()/push() change the query string that useSearchParams()
 * returns, and re-render its readers, the way a client navigation does.
 * notFound() throws, as the real one does.
 */
import { useMemo, useSyncExternalStore } from "react";

let pathname = "/";
let query = "";
let routeParams: Record<string, string | string[]> = {};
const listeners = new Set<() => void>();

function navigate(url: string) {
  const [path, search = ""] = url.split("?");
  if (path) pathname = path;
  query = search;
  listeners.forEach((listener) => listener());
}

/** Sets the current address before a render; no listeners are told. */
export function setLocation(url: string) {
  const [path, search = ""] = url.split("?");
  pathname = path || "/";
  query = search;
}

/** The dynamic segments useParams() returns, e.g. { id: "5" } for /admin/shops/[id]. */
export function setRouteParams(params: Record<string, string | string[]>) {
  routeParams = params;
}

/** The current query string as an object, for assertions. */
export function currentParams(): Record<string, string> {
  return Object.fromEntries(new URLSearchParams(query));
}

const router = {
  replace: navigate,
  push: navigate,
  back() {},
  forward() {},
  refresh() {},
  prefetch() {},
};

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useRouter() {
  return router;
}

export function usePathname() {
  return useSyncExternalStore(subscribe, () => pathname);
}

export function useSearchParams() {
  const current = useSyncExternalStore(subscribe, () => query);
  return useMemo(() => new URLSearchParams(current), [current]);
}

export function useParams<T extends Record<string, string | string[]>>(): T {
  return routeParams as T;
}

export function notFound(): never {
  throw new Error("NEXT_NOT_FOUND");
}
