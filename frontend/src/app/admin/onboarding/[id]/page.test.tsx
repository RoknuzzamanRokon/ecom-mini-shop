import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminOnboardingDetail, type AdminOnboardingSellerDetail } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { setRouteParams } from "@/test/navigation";

import AdminOnboardingDetailPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { is_superuser: true, permissions: [] } }) }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminOnboardingDetail: vi.fn(),
}));

function onboarding(overrides: Partial<AdminOnboardingSellerDetail> = {}): AdminOnboardingSellerDetail {
  return {
    id: 4,
    business_name: "Corner Store",
    seller_type: "LIMITED_SHOP_OWNER",
    status: "PENDING",
    rejection_reason: "",
    username: "corner_owner",
    phone: "+8801712345678",
    onboarded_by: "sales",
    shop_count: 1,
    product_count: 1,
    starting_points: 200,
    tokens_awarded: 51,
    created_at: "2026-10-30T10:00:00Z",
    business_email: "",
    business_phone: "01811111111",
    tax_id: "",
    description: "",
    email: "",
    first_name: "Karim",
    last_name: "",
    points_balance: 195,
    approved_at: null,
    reversed_at: null,
    points_returned: 0,
    tokens_taken_back: 0,
    shops: [
      {
        id: 9,
        name: "Corner Store Mirpur",
        slug: "corner-store-mirpur",
        status: "PENDING",
        rejection_reason: "",
        phone: "",
        additional_phones: [],
        address: "Mirpur 10",
        description: "",
        latitude: 23.807,
        longitude: 90.368,
        created_at: "2026-10-30T10:05:00Z",
        products: [
          {
            id: 31,
            name: "Rice 5kg",
            slug: "rice-5kg",
            category: "Grocery",
            price: "450.00",
            old_price: null,
            stock: 10,
            status: "SUBMITTED",
            rejection_reason: "",
            image_url: null,
            created_at: "2026-10-30T10:06:00Z",
          },
        ],
      },
    ],
    ...overrides,
  };
}

async function openDetail(data: AdminOnboardingSellerDetail) {
  vi.mocked(getAdminOnboardingDetail).mockResolvedValue(data);
  render(<AdminOnboardingDetailPage />);
  await act(async () => {});
}

beforeEach(() => {
  setRouteParams({ id: "4" });
  setTokens("access", "refresh");
  vi.mocked(getAdminOnboardingDetail).mockReset();
});

describe("Console onboarding detail", () => {
  it("shows what the Sales Team added, priced in Taka, with the decision buttons", async () => {
    await openDetail(onboarding());

    expect(getAdminOnboardingDetail).toHaveBeenCalledWith("access", "4");
    expect(screen.getByRole("heading", { name: "Corner Store" })).toBeInTheDocument();
    expect(screen.getByText("01712345678")).toBeInTheDocument();
    expect(screen.getByText("Corner Store Mirpur")).toBeInTheDocument();
    expect(screen.getByText("Rice 5kg")).toBeInTheDocument();
    expect(screen.getByText("৳450.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View on map/ })).toHaveAttribute(
      "href",
      "https://www.google.com/maps?q=23.807,90.368"
    );
    expect(screen.getByRole("button", { name: "Approve all" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("offers no decision once the seller is decided", async () => {
    await openDetail(
      onboarding({ status: "REJECTED", rejection_reason: "Fake shop", reversed_at: "2026-10-31T09:00:00Z", points_returned: 200, tokens_taken_back: 51 })
    );

    expect(screen.queryByRole("button", { name: "Approve all" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.getByText("Rejected: Fake shop")).toBeInTheDocument();
    expect(screen.getByText(/200 points, 51 tokens on/)).toBeInTheDocument();
  });
});
