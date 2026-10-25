import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminCategoryDetail, updateAdminCategory, type AdminCategory } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { setRouteParams } from "@/test/navigation";

import AdminCategoryDetailPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { is_superuser: true } }) }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminCategoryDetail: vi.fn(),
  updateAdminCategory: vi.fn(),
}));

const CATEGORY: AdminCategory = {
  id: 4, name: "Lamps", slug: "lamps", icon: "", image: null, description: "", is_active: true,
  products_count: 3, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  setRouteParams({ id: "4" });
  setTokens("access", "refresh");
  vi.mocked(getAdminCategoryDetail).mockReset().mockResolvedValue(CATEGORY);
  vi.mocked(updateAdminCategory).mockReset().mockResolvedValue({ ...CATEGORY, is_active: false });
});

async function untickActiveAndSave() {
  render(<AdminCategoryDetailPage />);
  fireEvent.click(await screen.findByRole("button", { name: /^Edit$/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Active/ }));
  fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
}

describe("Category detail: deactivating from the edit form (BUG-106)", () => {
  it("asks first, naming the products, and saves only once confirmed", async () => {
    await untickActiveAndSave();

    const dialog = screen.getByRole("dialog", { name: "Deactivate category?" });
    expect(within(dialog).getByText(/The 3 products filed under it/)).toBeInTheDocument();
    expect(updateAdminCategory).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate and save" }));
    });
    expect(updateAdminCategory).toHaveBeenCalledWith("access", 4, expect.objectContaining({ is_active: false }));
  });

  it("saves nothing when cancelled", async () => {
    await untickActiveAndSave();
    const dialog = screen.getByRole("dialog", { name: "Deactivate category?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(updateAdminCategory).not.toHaveBeenCalled();
  });
});
