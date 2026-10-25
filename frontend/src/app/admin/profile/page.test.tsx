import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMyStaffWallet, type StaffWalletSummary } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";

import AdminProfilePage from "./page";

const profileState = vi.hoisted(() => ({
  profile: null as null | { display_name: string; phone: string; avatar: null },
  error: null as string | null,
  isLoading: false,
}));

vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    isLoading: false,
    user: {
      id: 9, username: "finance_ops", first_name: "Nila", last_name: "Sen", email: "nila@example.com",
      is_staff: true, is_superuser: false, roles: ["FINANCE"], permissions: ["points.add", "points.view"],
    },
  }),
}));
vi.mock("@/context/ProfileContext", () => ({ useProfile: () => profileState }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getMyStaffWallet: vi.fn(),
}));

function wallet(overrides: Partial<StaffWalletSummary> = {}): StaffWalletSummary {
  return {
    has_wallet: true, balance: 0, received: 500, given_to_sellers: 100, sent_to_staff: 0, taken_back: 0,
    expired: 400, transaction_count: 3, can_mint: false, points_expire: true, expiry_enabled: true,
    expiry_months: 12, upcoming_expiries: [], recent: [],
    ...overrides,
  };
}

beforeEach(() => {
  setTokens("access", "refresh");
  profileState.profile = null;
  profileState.error = "You do not have permission to view this profile ('profile.view' required).";
  vi.mocked(getMyStaffWallet).mockReset().mockResolvedValue(wallet());
});

describe("Console profile", () => {
  it("says the profile is unavailable instead of “Not set”, and offers no edit link (BUG-112)", async () => {
    render(<AdminProfilePage />);

    expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: /Edit details/ })).not.toBeInTheDocument();
  });

  it("shows expired points, so the figures add up (BUG-113)", async () => {
    render(<AdminProfilePage />);
    expect(await screen.findByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("400")).toBeInTheDocument();
  });

  it("says “No points left”, not “No points yet”, after activity (BUG-114)", async () => {
    render(<AdminProfilePage />);
    expect(await screen.findByText(/No points left to give/)).toBeInTheDocument();
    expect(screen.queryByText(/No points yet/)).not.toBeInTheDocument();
  });
});
