import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminShops, type AdminShop } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import type { PaginatedResponse } from "@/lib/types";
import { currentParams, setLocation } from "@/test/navigation";

import AdminShopsPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
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
          owner_id: 7,
          owner_business_name: "Rahim",
          products_count: 0,
          created_at: "2026-01-01T00:00:00Z",
        }) as AdminShop
    ),
  };
}

beforeEach(() => {
  setLocation("/admin/shops");
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
    expect(currentParams()).toEqual({ status: "SUSPENDED" });

    await act(async () => {
      vi.advanceTimersByTime(349);
    });
    expect(currentParams()).toEqual({ status: "SUSPENDED" });
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(currentParams()).toEqual({ status: "SUSPENDED", search: "kettle" });
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
    expect(currentParams()).toEqual({});
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    expect(currentParams()).toEqual({ search: "ket" });
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

  it("lists one seller's shops by owner id and names them (BUG-081)", async () => {
    setLocation("/admin/shops?owner=7");
    vi.mocked(getAdminShops).mockResolvedValue(page("Corner Shop"));
    render(<AdminShopsPage />);

    expect(await screen.findByText("Corner Shop")).toBeInTheDocument();
    expect(getAdminShops).toHaveBeenCalledWith("access", expect.objectContaining({ owner: 7 }));
    expect(screen.getByRole("link", { name: "Rahim" })).toHaveAttribute("href", "/admin/sellers/7");

    fireEvent.click(screen.getByRole("button", { name: /Show all owners/ }));
    expect(currentParams()).toEqual({});
    await act(async () => {});
    expect(vi.mocked(getAdminShops).mock.lastCall?.[1]).toMatchObject({ owner: undefined });
  });
});
