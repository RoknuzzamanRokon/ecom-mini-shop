import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  InsufficientPointsError,
  getSellerListingSummary,
  getSellerProducts,
  renewSellerProduct,
} from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { ListingSummary, Product } from "@/lib/types";

import ListingOverview from "./ListingOverview";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getSellerListingSummary: vi.fn(),
  getSellerProducts: vi.fn(),
  renewSellerProduct: vi.fn(),
}));

const SUMMARY: ListingSummary = {
  total: 6,
  live: 3,
  ending_soon: 1,
  expired: 2,
  in_review: 1,
  not_live: 0,
  has_end_date: true,
  ending_soon_days: 7,
  first_period_months: 4,
  renewal_period_months: 2,
  renewal_points: 5,
};

function product(overrides: Partial<Product>): Product {
  return {
    id: 1,
    name: "Assam Tea",
    slug: "assam-tea",
    description: "Strong.",
    price: "250.00",
    stock: 4,
    is_active: true,
    status: "PUBLISHED",
    in_stock: true,
    live_until: "2026-11-04T06:00:00Z",
    created_at: "2026-07-01T06:00:00Z",
    ...overrides,
  };
}

const EXPIRED = product({ id: 2, name: "Darjeeling", status: "EXPIRED", live_until: "2026-10-20T06:00:00Z", stock: 0, in_stock: false });

function page(results: Product[]) {
  return { count: results.length, next: null, previous: null, results };
}

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(getSellerListingSummary).mockReset().mockResolvedValue(SUMMARY);
  vi.mocked(getSellerProducts).mockReset().mockResolvedValue(page([product({})]));
  vi.mocked(renewSellerProduct).mockReset();
});

describe("ListingOverview", () => {
  it("shows the counts and the products ending soon first", async () => {
    render(<ListingOverview />);

    expect(await screen.findByText("Assam Tea")).toBeInTheDocument();
    expect(getSellerProducts).toHaveBeenCalledWith("access", { listing: "ending_soon", page: 1, page_size: 10 });
    expect(screen.getByText("Within 7 days")).toBeInTheDocument();
    expect(screen.getByText(/A new product stays live 4 months/)).toBeInTheDocument();
    expect(screen.getByText(/Live until 04 Nov 2026/)).toBeInTheDocument();
  });

  it("lists expired products with their date and out-of-stock state", async () => {
    render(<ListingOverview />);
    await screen.findByText("Assam Tea");

    vi.mocked(getSellerProducts).mockResolvedValue(page([EXPIRED]));
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Expired" }));
    });

    expect(getSellerProducts).toHaveBeenLastCalledWith("access", { listing: "expired", page: 1, page_size: 10 });
    expect(screen.getByText(/Expired 20 Oct 2026 · Out of stock/)).toBeInTheDocument();
  });

  it("renews an expired product after a confirmation, then reloads", async () => {
    vi.mocked(getSellerProducts).mockResolvedValue(page([EXPIRED]));
    vi.mocked(renewSellerProduct).mockResolvedValue({
      ...EXPIRED,
      status: "PUBLISHED",
      live_until: "2027-01-01T06:00:00Z",
    });
    const onRenewed = vi.fn();
    render(<ListingOverview onRenewed={onRenewed} />);
    await screen.findByText("Darjeeling");

    fireEvent.click(screen.getByRole("button", { name: /Renew · 5 pts/ }));
    expect(renewSellerProduct).not.toHaveBeenCalled();
    expect(screen.getByText("Renew for 5 points?")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    });

    expect(renewSellerProduct).toHaveBeenCalledWith("access", 2);
    expect(screen.getByRole("status")).toHaveTextContent('"Darjeeling" is live again until 01 Jan 2027.');
    expect(onRenewed).toHaveBeenCalled();
    expect(getSellerListingSummary).toHaveBeenCalledTimes(2);
  });

  it("says how to get points when the wallet is short", async () => {
    vi.mocked(getSellerProducts).mockResolvedValue(page([EXPIRED]));
    vi.mocked(renewSellerProduct).mockRejectedValue(new InsufficientPointsError("Short", 5, 2));
    render(<ListingOverview />);
    await screen.findByText("Darjeeling");

    fireEvent.click(screen.getByRole("button", { name: /Renew · 5 pts/ }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Renewing needs 5 points and your wallet holds 2.");
  });

  it("tells a Full Shop Owner their products have no end date", async () => {
    vi.mocked(getSellerListingSummary).mockResolvedValue({ ...SUMMARY, has_end_date: false });
    render(<ListingOverview />);

    expect(await screen.findByText(/stay live with no end date/)).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByText("Expired")).not.toBeInTheDocument();
  });
});
