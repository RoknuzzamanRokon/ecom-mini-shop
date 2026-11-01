import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AdminApiError,
  cancelTokenPayout,
  getMyOnboardedSellers,
  getMyOnboardingSummary,
  getMyTokenPayouts,
  requestTokenPayout,
  sellPointsToOnboardedSeller,
  type AdminOnboarderSummary,
  type AdminOnboardingSeller,
  type AdminTokenPayout,
} from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";

import AdminMySellersPage from "./page";
import { quickAmounts, saleAmountError } from "./pointSale";
import { payoutTokensError } from "./TokenPayoutPanel";

const auth = vi.hoisted(() => ({ user: null as { is_superuser: boolean; permissions: string[] } | null }));

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getMyOnboardingSummary: vi.fn(),
  getMyOnboardedSellers: vi.fn(),
  sellPointsToOnboardedSeller: vi.fn(),
  getMyTokenPayouts: vi.fn(),
  requestTokenPayout: vi.fn(),
  cancelTokenPayout: vi.fn(),
}));

const SUMMARY: AdminOnboarderSummary = {
  points: 1000,
  tokens: 102,
  taka_per_token: 1,
  pending_payout_tokens: 0,
  starting_points: 200,
  tokens_per_seller: 51,
  product_creation_cost: 5,
  minimum_point_sale: 100,
  can_onboard: true,
  sellers: { total: 2, awaiting_approval: 1, live: 1, rejected: 0 },
};

function seller(overrides: Partial<AdminOnboardingSeller>): AdminOnboardingSeller {
  return {
    id: 4,
    business_name: "Corner Store",
    seller_type: "LIMITED_SHOP_OWNER",
    status: "ACTIVE",
    rejection_reason: "",
    username: "corner_owner",
    phone: "+8801712345678",
    onboarded_by: "sales",
    shop_count: 1,
    product_count: 2,
    starting_points: 200,
    tokens_awarded: 51,
    created_at: "2026-10-30T10:00:00Z",
    ...overrides,
  };
}

const CORNER = seller({});
const WAITING = seller({ id: 5, business_name: "New Tea Stall", username: "tea_stall", status: "PENDING" });

async function openPage() {
  render(<AdminMySellersPage />);
  await act(async () => {});
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  auth.user = { is_superuser: false, permissions: ["sellers.onboard"] };
  setTokens("access", "refresh");
  vi.mocked(getMyOnboardingSummary).mockReset().mockResolvedValue(SUMMARY);
  vi.mocked(getMyOnboardedSellers)
    .mockReset()
    .mockResolvedValue({ count: 2, next: null, previous: null, results: [CORNER, WAITING] });
  vi.mocked(sellPointsToOnboardedSeller).mockReset();
  vi.mocked(getMyTokenPayouts).mockReset().mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  vi.mocked(requestTokenPayout).mockReset();
  vi.mocked(cancelTokenPayout).mockReset();
});

const PENDING: AdminTokenPayout = {
  id: 7,
  requested_by: "sales",
  tokens: 100,
  taka_per_token: 1,
  amount_taka: 100,
  note: "bKash 01711111111",
  status: "PENDING",
  decided_by: null,
  decided_at: null,
  decision_note: "",
  created_at: "2026-11-02T06:00:00Z",
};

describe("point sale helpers", () => {
  it("refuses blanks, fractions, amounts below the minimum and above the wallet", () => {
    expect(saleAmountError("", 100, 1000)).toBe("Enter a whole number of points.");
    expect(saleAmountError("150.5", 100, 1000)).toBe("Enter a whole number of points.");
    expect(saleAmountError("99", 100, 1000)).toBe("The minimum sale is 100 points.");
    expect(saleAmountError("1001", 100, 1000)).toBe("Your wallet holds 1,000 points.");
    expect(saleAmountError("300", 100, 1000)).toBeNull();
  });

  it("offers quick amounts the wallet can cover", () => {
    expect(quickAmounts(100, 600)).toEqual([100, 200, 500]);
    expect(quickAmounts(250, 2000)).toEqual([250, 500, 1000]);
    expect(quickAmounts(100, 50)).toEqual([]);
  });
});

describe("My Sellers page", () => {
  it("shows the wallet, tokens and sellers, with Sell points only on approved ones", async () => {
    await openPage();

    expect(screen.getByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("Minimum sale: 100 points")).toBeInTheDocument();
    expect(screen.getByText("51 for each seller you onboard")).toBeInTheDocument();
    expect(screen.getAllByText("Corner Store").length).toBeGreaterThan(0);
    expect(screen.getAllByText("New Tea Stall").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Sell points" })).toHaveLength(1);
  });

  it("sells points after the amount is valid, then reports the new balances", async () => {
    vi.mocked(sellPointsToOnboardedSeller).mockResolvedValue({
      seller_id: 4,
      amount: 300,
      points_balance: 450,
      points_expire_at: "2026-12-01T06:00:00Z",
      your_points: 700,
    });
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Sell points" }));
    expect(dialog().getByText("Sell points to Corner Store")).toBeInTheDocument();
    const input = dialog().getByLabelText("Points");

    fireEvent.change(input, { target: { value: "50" } });
    expect(dialog().getByText("The minimum sale is 100 points.")).toBeInTheDocument();
    expect(dialog().getByRole("button", { name: "Sell points" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "300" } });
    expect(dialog().getByText("Your wallet: 1,000 → 700 points.")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Sell 300 points" }));
    });

    expect(sellPointsToOnboardedSeller).toHaveBeenCalledWith("access", 4, 300);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Sold 300 points to Corner Store. They now hold 450 points, valid until 01 Dec 2026. Your wallet holds 700."
    );
    expect(screen.getByText("700")).toBeInTheDocument();
  });

  it("keeps the dialog open with the server's reason when a sale is refused", async () => {
    vi.mocked(sellPointsToOnboardedSeller).mockRejectedValue(
      new AdminApiError("Your wallet holds 250 points.", 400, { available_points: 250 })
    );
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Sell points" }));
    fireEvent.click(dialog().getByRole("button", { name: "500" }));
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Sell 500 points" }));
    });

    expect(dialog().getByRole("alert")).toHaveTextContent("Your wallet holds 250 points.");
    // The wallet figure follows the server, so the same amount is now refused here.
    expect(dialog().getByText("Your wallet holds 250 points.", { selector: "p" })).toBeInTheDocument();
    expect(dialog().getByRole("button", { name: "Sell points" })).toBeDisabled();
  });

  it("says when the wallet is below the minimum sale", async () => {
    vi.mocked(getMyOnboardingSummary).mockResolvedValue({ ...SUMMARY, points: 60 });
    await openPage();

    expect(screen.getByRole("note")).toHaveTextContent("fewer points than the minimum sale of 100");
    expect(screen.getByRole("button", { name: "Sell points" })).toBeDisabled();
  });

  it("links each seller to its own page", async () => {
    await openPage();
    expect(screen.getAllByRole("link", { name: "Corner Store" })[0]).toHaveAttribute("href", "/admin/my-sellers/4");
  });

  it("hands tokens in for payment, worth ৳1 each", async () => {
    vi.mocked(requestTokenPayout).mockResolvedValue(PENDING);
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Request payment" }));
    const input = dialog().getByLabelText("Tokens");
    fireEvent.change(input, { target: { value: "103" } });
    expect(dialog().getByText("You hold 102 tokens.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "100" } });
    fireEvent.change(dialog().getByLabelText("Note for the admin"), { target: { value: "bKash 01711111111" } });
    expect(dialog().getByText("Worth ৳100; 2 tokens stay with you.")).toBeInTheDocument();

    vi.mocked(getMyTokenPayouts).mockResolvedValue({ count: 1, next: null, previous: null, results: [PENDING] });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Request ৳100" }));
    });

    expect(requestTokenPayout).toHaveBeenCalledWith("access", 100, "bKash 01711111111");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for an admin: 100 tokens, ৳100");
    expect(screen.queryByRole("button", { name: "Request payment" })).not.toBeInTheDocument();
  });

  it("cancels a waiting request", async () => {
    vi.mocked(getMyTokenPayouts).mockResolvedValue({ count: 1, next: null, previous: null, results: [PENDING] });
    vi.mocked(cancelTokenPayout).mockResolvedValue({ ...PENDING, status: "CANCELLED" });
    await openPage();

    vi.mocked(getMyTokenPayouts).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ ...PENDING, status: "CANCELLED" }],
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    });

    expect(cancelTokenPayout).toHaveBeenCalledWith("access", 7);
    expect(screen.getByRole("button", { name: "Request payment" })).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("checks the token amount", () => {
    expect(payoutTokensError("", 50)).toBe("Enter a whole number of tokens.");
    expect(payoutTokensError("0", 50)).toBe("Ask for at least 1 token.");
    expect(payoutTokensError("51", 50)).toBe("You hold 50 tokens.");
    expect(payoutTokensError("50", 50)).toBeNull();
  });

  it("shows the access notice without asking the server", async () => {
    auth.user = { is_superuser: false, permissions: ["points.view"] };
    await openPage();

    expect(screen.getByText("Insufficient Permissions")).toBeInTheDocument();
    expect(getMyOnboardingSummary).not.toHaveBeenCalled();
  });
});
