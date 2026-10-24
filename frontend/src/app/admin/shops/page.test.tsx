import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminShops, type AdminShop } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import type { PaginatedResponse } from "@/lib/types";

import AdminShopsPage from "./page";

// A stand-in for the App Router: replace() changes the query string the page
// reads back through useSearchParams, the way a client navigation does.
const nav = vi.hoisted(() => {
  let query = "";
  const listeners = new Set<() => void>();
  return {
    query: () => query,
    reset() {
      query = "";
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    router: {
      replace(url: string) {
        query = url.split("?")[1] ?? "";
        listeners.forEach((listener) => listener());
      },
      push() {},
      prefetch() {},
    },
  };
});

vi.mock("next/navigation", async () => {
  const { useMemo, useSyncExternalStore } = await import("react");
  return {
    usePathname: () => "/admin/shops",
    useRouter: () => nav.router,
    useSearchParams: () => {
      const query = useSyncExternalStore(nav.subscribe, nav.query);
      return useMemo(() => new URLSearchParams(query), [query]);
    },
  };
});
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: null }) }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminShops: vi.fn(),
}));

function page(...names: string[]): PaginatedResponse<AdminShop> {
  return {
    count: names.length,
    next: null,
    previous: null,
    results: names.map(
      (name, index) =>
        ({
          id: index + 1,
          name,
          slug: name.toLowerCase().replace(/ /g, "-"),
          status: "ACTIVE",
          owner_business_name: "Owner",
          products_count: 0,
          created_at: "2026-01-01T00:00:00Z",
        }) as AdminShop
    ),
  };
}

const params = () => Object.fromEntries(new URLSearchParams(nav.query()));

beforeEach(() => {
  nav.reset();
  setTokens("access", "refresh");
  vi.mocked(getAdminShops).mockReset();
});

describe("Console shops list", () => {
  it("keeps a filter chosen while the typed search is still waiting to apply (BUG-074)", async () => {
    vi.useFakeTimers();
    vi.mocked(getAdminShops).mockResolvedValue(page());
    render(<AdminShopsPage />);
    await act(async () => {});

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "kettle" } });
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "SUSPENDED" } });
    expect(params()).toEqual({ status: "SUSPENDED" });

    await act(async () => {
      vi.advanceTimersByTime(349);
    });
    expect(params()).toEqual({ status: "SUSPENDED" });
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(params()).toEqual({ status: "SUSPENDED", search: "kettle" });
    expect(screen.getByLabelText("Search")).toHaveValue("kettle");
  });

  it("applies the search once typing pauses, not per keystroke", async () => {
    vi.useFakeTimers();
    vi.mocked(getAdminShops).mockResolvedValue(page());
    render(<AdminShopsPage />);
    await act(async () => {});

    for (const text of ["k", "ke", "ket"]) {
      fireEvent.change(screen.getByLabelText("Search"), { target: { value: text } });
      await act(async () => {
        vi.advanceTimersByTime(100);
      });
    }
    expect(params()).toEqual({});
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    expect(params()).toEqual({ search: "ket" });
    expect(vi.mocked(getAdminShops).mock.calls.map(([, filters]) => filters?.search)).toEqual([undefined, "ket"]);
  });

  it("shows the newest filter's shops when an older request answers last (BUG-073)", async () => {
    let answerFirst!: (value: PaginatedResponse<AdminShop>) => void;
    vi.mocked(getAdminShops)
      .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
      .mockResolvedValueOnce(page("Suspended Shop"));
    render(<AdminShopsPage />);

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "SUSPENDED" } });
    expect(await screen.findByText("Suspended Shop")).toBeInTheDocument();
    await act(async () => {
      answerFirst(page("Every Shop"));
    });

    expect(screen.queryByText("Every Shop")).not.toBeInTheDocument();
    expect(screen.getByText("Suspended Shop")).toBeInTheDocument();
  });
});
