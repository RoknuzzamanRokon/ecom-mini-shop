import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  acceptTokenPayout,
  getTokenPayoutQueue,
  rejectTokenPayout,
  type AdminTokenPayout,
} from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { currentParams, setLocation } from "@/test/navigation";

import AdminTokenPayoutsPage from "./page";

const auth = vi.hoisted(() => ({
  user: null as { username: string; is_superuser: boolean; permissions: string[] } | null,
}));

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getTokenPayoutQueue: vi.fn(),
  acceptTokenPayout: vi.fn(),
  rejectTokenPayout: vi.fn(),
}));

const REQUEST: AdminTokenPayout = {
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

function queue(results: AdminTokenPayout[], yourTokens = 0) {
  return { count: results.length, next: null, previous: null, results, your_tokens: yourTokens };
}

async function openPage() {
  render(<AdminTokenPayoutsPage />);
  await act(async () => {});
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  setLocation("/admin/token-payouts");
  auth.user = { username: "admin", is_superuser: false, permissions: ["onboarding.payouts.manage"] };
  setTokens("access", "refresh");
  vi.mocked(getTokenPayoutQueue).mockReset().mockResolvedValue(queue([REQUEST]));
  vi.mocked(acceptTokenPayout).mockReset();
  vi.mocked(rejectTokenPayout).mockReset();
});

describe("Token Payouts page", () => {
  it("lists waiting requests in ৳", async () => {
    await openPage();
    expect(getTokenPayoutQueue).toHaveBeenCalledWith("access", { status: "PENDING", page: 1 });
    expect(screen.getAllByText("@sales").length).toBeGreaterThan(0);
    expect(screen.getAllByText("100 / ৳100").length).toBeGreaterThan(0);
  });

  it("accepts with an optional payment note, and the tokens become the admin's", async () => {
    vi.mocked(acceptTokenPayout).mockResolvedValue({ ...REQUEST, status: "ACCEPTED", decided_by: "admin" });
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(dialog().getByText(/Accept only after paying @sales ৳100/)).toBeInTheDocument();
    fireEvent.change(dialog().getByRole("textbox"), { target: { value: "bKash TrxID 8N7" } });
    vi.mocked(getTokenPayoutQueue).mockResolvedValue(queue([], 100));
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Accept" }));
    });

    expect(acceptTokenPayout).toHaveBeenCalledWith("access", 7, "bKash TrxID 8N7");
    expect(screen.getByRole("status")).toHaveTextContent("Accepted: 100 tokens from @sales are now yours (৳100).");
  });

  it("needs a reason to reject", async () => {
    vi.mocked(rejectTokenPayout).mockResolvedValue({ ...REQUEST, status: "REJECTED" });
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(dialog().getByRole("button", { name: "Reject" })).toBeDisabled();
    fireEvent.change(dialog().getByRole("textbox"), { target: { value: "Not this month" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Reject" }));
    });

    expect(rejectTokenPayout).toHaveBeenCalledWith("access", 7, "Not this month");
    expect(screen.getByRole("status")).toHaveTextContent("Rejected: 100 tokens went back to @sales.");
  });

  it("offers no decision on one's own request", async () => {
    auth.user = { username: "sales", is_superuser: false, permissions: ["onboarding.payouts.manage"] };
    await openPage();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
  });

  it("switches to every request", async () => {
    await openPage();
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "All" }));
    });
    expect(currentParams()).toEqual({ view: "all" });
    expect(getTokenPayoutQueue).toHaveBeenLastCalledWith("access", { status: undefined, page: 1 });
  });

  it("shows the access notice without asking the server", async () => {
    auth.user = { username: "sales", is_superuser: false, permissions: ["sellers.onboard"] };
    await openPage();
    expect(screen.getByText("Insufficient Permissions")).toBeInTheDocument();
    expect(getTokenPayoutQueue).not.toHaveBeenCalled();
  });
});
