import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminApiError, getAdminCategories, updateAdminCategory, type AdminCategory } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { setLocation } from "@/test/navigation";

import { deactivationSummary } from "./categoryGovernance";
import AdminCategoriesPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { is_superuser: true } }) }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminCategories: vi.fn(),
  updateAdminCategory: vi.fn(),
}));

function category(overrides: Partial<AdminCategory> = {}): AdminCategory {
  return {
    id: 4,
    name: "Electronics",
    slug: "electronics",
    icon: "",
    image: null,
    description: "",
    is_active: true,
    products_count: 12,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

async function renderWith(row: AdminCategory) {
  vi.mocked(getAdminCategories).mockResolvedValue({ count: 1, next: null, previous: null, results: [row] });
  render(<AdminCategoriesPage />);
  await screen.findByText(row.name);
}

beforeEach(() => {
  setLocation("/admin/categories");
  setTokens("access", "refresh");
  vi.mocked(getAdminCategories).mockReset();
  vi.mocked(updateAdminCategory).mockReset();
});

describe("Console categories: deactivation (BUG-077)", () => {
  it("asks first, naming the products that leave the storefront, and sends nothing until confirmed", async () => {
    await renderWith(category());

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    const dialog = screen.getByRole("dialog", { name: "Deactivate category?" });
    expect(within(dialog).getByText(/The 12 products filed under it/)).toBeInTheDocument();
    expect(updateAdminCategory).not.toHaveBeenCalled();

    vi.mocked(updateAdminCategory).mockResolvedValue(category({ is_active: false }));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    });

    expect(updateAdminCategory).toHaveBeenCalledWith("access", 4, { is_active: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText('Category "Electronics" is now inactive.')).toBeInTheDocument();
  });

  it("changes nothing when cancelled", async () => {
    await renderWith(category());

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(updateAdminCategory).not.toHaveBeenCalled();
  });

  it("keeps the dialog open with the server's reason when the change fails", async () => {
    await renderWith(category());
    vi.mocked(updateAdminCategory).mockRejectedValue(new AdminApiError("Category is locked.", 400));

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    const dialog = screen.getByRole("dialog");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    });

    expect(within(dialog).getByText("Category is locked.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("activates an inactive category in one click", async () => {
    await renderWith(category({ is_active: false }));
    vi.mocked(updateAdminCategory).mockResolvedValue(category({ is_active: true }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(updateAdminCategory).toHaveBeenCalledWith("access", 4, { is_active: true });
  });
});

describe("deactivationSummary", () => {
  it.each([
    [0, "It has no products, so no listing changes."],
    [1, "The 1 product filed under it will not be shown"],
    [1250, "The 1,250 products filed under it will not be shown"],
  ])("describes %i products", (count, expected) => {
    expect(deactivationSummary(category({ products_count: count }))).toContain(expected);
  });
});
