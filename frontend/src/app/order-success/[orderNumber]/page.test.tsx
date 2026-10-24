import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getOrderDetail } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { setRouteParams } from "@/test/navigation";

import OrderSuccessPage from "./page";

const auth = vi.hoisted(() => ({ isAuthenticated: true, isLoading: false }));

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/components/layout/StorefrontChrome", () => ({ default: () => null }));
vi.mock("@/components/layout/Footer", () => ({ default: () => null }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getOrderDetail: vi.fn(),
}));

const ORDER = {
  id: 1,
  order_number: "MS-1001",
  status: "PENDING",
  customer_name: "Nadia",
  shipping_recipient_name: "Nadia Islam",
  total_amount: "1060.00",
} as Order;

beforeEach(() => {
  auth.isAuthenticated = true;
  auth.isLoading = false;
  setTokens("access", "refresh");
  setRouteParams({ orderNumber: "MS-1001" });
  vi.mocked(getOrderDetail).mockReset();
});

describe("Order success page (BUG-089)", () => {
  it("confirms an order read back from the account", async () => {
    vi.mocked(getOrderDetail).mockResolvedValue(ORDER);
    render(<OrderSuccessPage />);

    expect(await screen.findByText("Order Confirmed")).toBeInTheDocument();
    expect(screen.getByText("Nadia Islam")).toBeInTheDocument();
    expect(screen.getByText("৳1060.00")).toBeInTheDocument();
    expect(getOrderDetail).toHaveBeenCalledWith("MS-1001", "access");
  });

  it("says not found, not confirmed, for an unknown number", async () => {
    setRouteParams({ orderNumber: "NOPE" });
    vi.mocked(getOrderDetail).mockResolvedValue(null);
    render(<OrderSuccessPage />);

    expect(await screen.findByRole("heading", { name: "Order not found" })).toBeInTheDocument();
    expect(screen.queryByText("Order Confirmed")).not.toBeInTheDocument();
  });

  it("shows an error with a working retry when the order cannot be read", async () => {
    vi.mocked(getOrderDetail).mockRejectedValueOnce(new Error("Bad gateway")).mockResolvedValueOnce(ORDER);
    render(<OrderSuccessPage />);

    expect(await screen.findByText("We couldn't load this order")).toBeInTheDocument();
    expect(screen.queryByText("Order Confirmed")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Try Again/i }));
    });
    expect(await screen.findByText("Order Confirmed")).toBeInTheDocument();
  });

  it("shows a spinner, not a confirmation, while loading", () => {
    vi.mocked(getOrderDetail).mockReturnValue(new Promise(() => {}));
    render(<OrderSuccessPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading your order…");
    expect(screen.queryByText("Order Confirmed")).not.toBeInTheDocument();
  });

  it("asks a signed-out visitor to sign in, without a request", async () => {
    auth.isAuthenticated = false;
    render(<OrderSuccessPage />);

    expect(screen.getByRole("link", { name: "Sign In" })).toHaveAttribute(
      "href",
      "/login?next=%2Forder-success%2FMS-1001"
    );
    expect(getOrderDetail).not.toHaveBeenCalled();
  });
});
