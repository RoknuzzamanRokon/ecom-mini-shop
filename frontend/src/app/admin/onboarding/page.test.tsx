import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  approveAdminOnboarding,
  getAdminOnboardingQueue,
  rejectAdminOnboarding,
  type AdminOnboardingApproveResult,
  type AdminOnboardingSeller,
  type AdminOnboardingSellerDetail,
} from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { setLocation } from "@/test/navigation";

import AdminOnboardingPage from "./page";

const auth = vi.hoisted(() => ({ user: null as { is_superuser: boolean; permissions: string[] } | null }));

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminOnboardingQueue: vi.fn(),
  approveAdminOnboarding: vi.fn(),
  rejectAdminOnboarding: vi.fn(),
}));

const CORNER: AdminOnboardingSeller = {
  id: 4,
  business_name: "Corner Store",
  seller_type: "FULL_SHOP_OWNER",
  status: "PENDING",
  rejection_reason: "",
  username: "corner_owner",
  phone: "+8801712345678",
  onboarded_by: "sales",
  shop_count: 1,
  product_count: 2,
  starting_points: 200,
  tokens_awarded: 51,
  created_at: "2026-10-30T10:00:00Z",
};

function detail(overrides: Partial<AdminOnboardingSellerDetail> = {}): AdminOnboardingSellerDetail {
  return {
    ...CORNER,
    business_email: "",
    business_phone: "",
    tax_id: "",
    description: "",
    email: "",
    first_name: "",
    last_name: "",
    points_balance: 190,
    approved_at: null,
    reversed_at: null,
    points_returned: 0,
    tokens_taken_back: 0,
    shops: [],
    ...overrides,
  };
}

async function openQueue() {
  render(<AdminOnboardingPage />);
  await act(async () => {});
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  auth.user = { is_superuser: false, permissions: ["sellers.approve", "shops.approve", "products.approve", "products.publish"] };
  setLocation("/admin/onboarding");
  setTokens("access", "refresh");
  vi.mocked(getAdminOnboardingQueue).mockReset().mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [CORNER],
  });
  vi.mocked(approveAdminOnboarding).mockReset();
  vi.mocked(rejectAdminOnboarding).mockReset();
});

describe("Console onboarding queue", () => {
  it("approves a seller with its shop and products in one step", async () => {
    vi.mocked(approveAdminOnboarding).mockResolvedValue({
      ...detail({ status: "ACTIVE", approved_at: "2026-10-31T09:00:00Z" }),
      shops_approved: 1,
      products_published: 2,
    } as AdminOnboardingApproveResult);
    await openQueue();
    expect(screen.getByText("Corner Store")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve all" }));
    expect(dialog().getByText(/all go live together/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Approve all" }));
    });

    expect(approveAdminOnboarding).toHaveBeenCalledWith("access", 4);
    expect(screen.queryByText("Corner Store")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent('"Corner Store" is live with 1 shop and 2 products.');
  });

  it("rejects only with a reason, and says what went back to the onboarder", async () => {
    vi.mocked(rejectAdminOnboarding).mockResolvedValue(
      detail({ status: "REJECTED", rejection_reason: "Fake shop", points_returned: 200, tokens_taken_back: 51 })
    );
    await openQueue();

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(dialog().getByText(/200 starting points go back to @sales/)).toBeInTheDocument();
    expect(dialog().getByRole("button", { name: "Reject" })).toBeDisabled();

    fireEvent.change(dialog().getByLabelText(/Reason/), { target: { value: "Fake shop" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Reject" }));
    });

    expect(rejectAdminOnboarding).toHaveBeenCalledWith("access", 4, "Fake shop");
    expect(screen.getByRole("status")).toHaveTextContent("200 points went back to @sales and 51 tokens were taken back.");
  });

  it("keeps the dialog open with the backend's message when the decision fails", async () => {
    const { AdminApiError } = await vi.importActual<typeof import("@/lib/admin-api")>("@/lib/admin-api");
    vi.mocked(approveAdminOnboarding).mockRejectedValue(
      new AdminApiError("Only a seller awaiting approval can be approved with its onboarding; this one is ACTIVE.", 400)
    );
    await openQueue();

    fireEvent.click(screen.getByRole("button", { name: "Approve all" }));
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Approve all" }));
    });

    expect(dialog().getByText(/this one is ACTIVE/)).toBeInTheDocument();
    expect(screen.getByText("Corner Store")).toBeInTheDocument();
  });

  it("shows a Sales Manager the access notice without asking the server", async () => {
    auth.user = { is_superuser: false, permissions: ["sellers.approve", "sellers.view"] };
    await openQueue();

    expect(screen.getByText("Insufficient Permissions")).toBeInTheDocument();
    expect(getAdminOnboardingQueue).not.toHaveBeenCalled();
  });
});
