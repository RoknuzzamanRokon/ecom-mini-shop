import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminMetrics, type AdminMetrics } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";

import AdminDashboardPage from "./page";

const auth = vi.hoisted(() => ({ user: null as { permissions: string[] } | null }));

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminMetrics: vi.fn(),
}));

const METRICS: AdminMetrics = {
  total_orders: 1234,
  total_revenue: 56000,
  pending_shops: 2,
  pending_sellers: 0,
  total_shops: 40,
  total_sellers: 31,
  total_products: 900,
};

function signInWith(...permissions: string[]) {
  auth.user = { permissions };
}

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(getAdminMetrics).mockReset().mockResolvedValue(METRICS);
});

describe("Console dashboard KPIs (BUG-083)", () => {
  it("asks for no metrics and shows no figures without reports.view", async () => {
    // SALES_TEAM: order and product codes, but not reports.view.
    signInWith("orders.view", "orders.staff.view", "products.view");
    render(<AdminDashboardPage />);

    expect(await screen.findByText("No metrics available")).toBeInTheDocument();
    expect(getAdminMetrics).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Total Orders")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Refresh Data/ })).not.toBeInTheDocument();
  });

  it("shows the cards reports.view and each card's own code allow", async () => {
    signInWith("reports.view", "orders.staff.view", "shops.view");
    render(<AdminDashboardPage />);

    expect(await screen.findByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("Pending Shops")).toBeInTheDocument();
    expect(screen.queryByText("Pending Sellers")).not.toBeInTheDocument();
    expect(getAdminMetrics).toHaveBeenCalledTimes(1);
  });

  it("hides revenue without payments.view, which the API needs to send it", async () => {
    signInWith("reports.view", "orders.staff.view");
    const withoutRevenue: AdminMetrics = { ...METRICS };
    delete withoutRevenue.total_revenue;
    vi.mocked(getAdminMetrics).mockResolvedValue(withoutRevenue);
    render(<AdminDashboardPage />);

    expect(await screen.findByText("1,234")).toBeInTheDocument();
    expect(screen.queryByText("Total Revenue")).not.toBeInTheDocument();
    expect(screen.queryByText(/৳/)).not.toBeInTheDocument();
  });

  it("shows revenue in ৳ to holders of payments.view", async () => {
    signInWith("reports.view", "payments.view");
    render(<AdminDashboardPage />);

    expect(await screen.findByText("Total Revenue")).toBeInTheDocument();
    expect(await screen.findByText(/৳\s?56,000/)).toBeInTheDocument();
  });
});
