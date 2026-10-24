import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminShopDetail, type AdminShop } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { getCurrentPosition, type CurrentPosition } from "@/lib/geolocation";
import { setRouteParams } from "@/test/navigation";

import AdminShopDetailPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { is_superuser: true } }) }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminShopDetail: vi.fn(),
}));
vi.mock("@/lib/geolocation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/geolocation")>()),
  getCurrentPosition: vi.fn(),
}));

const SHOP: AdminShop = {
  id: 5,
  owner_id: 7,
  owner_business_name: "Rahim",
  name: "Corner Shop",
  slug: "corner-shop",
  description: "",
  phone: "01711111111",
  additional_phones: [],
  address: "Road 1, Dhaka",
  latitude: null,
  longitude: null,
  status: "ACTIVE",
  rejection_reason: "",
  suspension_reason: "",
  products_count: 0,
  reviewed_at: null,
  approved_at: null,
  suspended_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const FIX: CurrentPosition = { latitude: 23.8103, longitude: 90.4125, accuracy: 12, timestamp: 0 };

beforeEach(() => {
  setRouteParams({ id: "5" });
  setTokens("access", "refresh");
  vi.mocked(getAdminShopDetail).mockReset().mockResolvedValue(SHOP);
});

describe("Console shop detail: Use My Current Location (BUG-078)", () => {
  it("keeps edits typed while the location prompt was open", async () => {
    let locate!: (position: CurrentPosition) => void;
    vi.mocked(getCurrentPosition).mockReturnValue(new Promise((resolve) => (locate = resolve)));
    render(<AdminShopDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit details/ }));

    fireEvent.click(screen.getByRole("button", { name: /Use My Current Location/ }));
    fireEvent.change(screen.getByLabelText(/Shop name/), { target: { value: "Corner Shop & Cafe" } });
    await act(async () => {
      locate(FIX);
    });

    expect(screen.getByLabelText(/Shop name/)).toHaveValue("Corner Shop & Cafe");
    expect(screen.getByLabelText(/Latitude/)).toHaveValue(23.8103);
    expect(screen.getByLabelText(/Longitude/)).toHaveValue(90.4125);
  });

  it("leaves a closed form closed when the fix arrives after Cancel", async () => {
    let locate!: (position: CurrentPosition) => void;
    vi.mocked(getCurrentPosition).mockReturnValue(new Promise((resolve) => (locate = resolve)));
    render(<AdminShopDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit details/ }));

    fireEvent.click(screen.getByRole("button", { name: /Use My Current Location/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/ }));
    await act(async () => {
      locate(FIX);
    });

    expect(screen.queryByLabelText(/Shop name/)).not.toBeInTheDocument();
  });
});
