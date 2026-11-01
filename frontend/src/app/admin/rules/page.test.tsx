import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminApiError, getAdminRules, updateAdminRules, type AdminRules } from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";

import AdminRulesPage from "./page";
import { draftError, formatRuleValue, pendingChanges } from "./ruleDrafts";

const auth = vi.hoisted(() => ({ user: null as { is_superuser: boolean; permissions: string[] } | null }));

vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getAdminRules: vi.fn(),
  updateAdminRules: vi.fn(),
}));

function rules(overrides: Partial<AdminRules> = {}): AdminRules {
  return {
    can_manage: true,
    checks: ["Onboarding starting points are 0 or at least the minimum point sale."],
    groups: [
      {
        key: "products",
        title: "Products",
        fixed: ["A Full Shop Owner's products have no end date."],
        rules: [
          {
            key: "product.creation_cost",
            label: "Product creation cost",
            help: "Points taken from the seller's wallet for each new product.",
            unit: "points",
            value: 5,
            default: 5,
            minimum: 1,
            maximum: 1000,
            applies_to: "Every seller",
            takes_effect: "The next product created",
            last_change: null,
          },
        ],
      },
      {
        key: "points",
        title: "Points",
        fixed: [],
        rules: [
          {
            key: "points.minimum_purchase",
            label: "Minimum point sale",
            help: "The fewest points staff may give a seller at once.",
            unit: "points",
            value: 100,
            default: 100,
            minimum: 1,
            maximum: 100000,
            applies_to: "Every seller",
            takes_effect: "The next sale",
            last_change: { at: "2026-10-30T10:00:00Z", by: "boss", reason: "Launch" },
          },
        ],
      },
    ],
    ...overrides,
  };
}

async function openPage() {
  render(<AdminRulesPage />);
  await act(async () => {});
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  auth.user = { is_superuser: false, permissions: ["rules.view", "rules.manage"] };
  setTokens("access", "refresh");
  vi.mocked(getAdminRules).mockReset().mockResolvedValue(rules());
  vi.mocked(updateAdminRules).mockReset();
});

describe("rule drafts", () => {
  const rule = rules().groups[0].rules[0];

  it("formats values with a singular unit for one", () => {
    expect(formatRuleValue(1, "months")).toBe("1 month");
    expect(formatRuleValue(1200, "points")).toBe("1,200 points");
  });

  it("refuses blanks, fractions and values out of range", () => {
    expect(draftError(rule, "")).toBe("Enter a whole number.");
    expect(draftError(rule, "2.5")).toBe("Enter a whole number.");
    expect(draftError(rule, "0")).toBe("Use 1 to 1,000 points.");
    expect(draftError(rule, "8")).toBeNull();
  });

  it("lists only the drafts that change a value", () => {
    const groups = rules().groups;
    expect(pendingChanges(groups, { "product.creation_cost": "5", "points.minimum_purchase": "150" })).toEqual([
      { rule: groups[1].rules[0], to: 150 },
    ]);
  });
});

describe("Console rules page", () => {
  it("shows every group with its values, defaults, last change and fixed rules", async () => {
    await openPage();

    expect(screen.getByRole("heading", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByLabelText("Product creation cost")).toHaveValue(5);
    expect(screen.getByText(/Changed 30 Oct 2026 by @boss/)).toBeInTheDocument();
    expect(screen.getByText("A Full Shop Owner's products have no end date.")).toBeInTheDocument();
    expect(screen.getByText(/starting points are 0 or at least/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review & save" })).not.toBeInTheDocument();
  });

  it("saves the changes with a reason after showing old and new values", async () => {
    vi.mocked(updateAdminRules).mockImplementation(async () => {
      const saved = rules();
      saved.groups[0].rules[0].value = 8;
      return { ...saved, changed: [{ key: "product.creation_cost", from: 5, to: 8 }] };
    });
    await openPage();

    fireEvent.change(screen.getByLabelText("Product creation cost"), { target: { value: "8" } });
    expect(screen.getByText("Was 5 points")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review & save" }));

    expect(dialog().getByText(/5 points →/)).toBeInTheDocument();
    expect(dialog().getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(dialog().getByLabelText(/Why are the rules changing/), { target: { value: "New prices" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save" }));
    });

    expect(updateAdminRules).toHaveBeenCalledWith(
      "access",
      { "product.creation_cost": { from: 5, to: 8 } },
      "New prices"
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved 1 change.");
    expect(screen.getByLabelText("Product creation cost")).toHaveValue(8);
  });

  it("blocks saving while a value is out of range", async () => {
    await openPage();

    fireEvent.change(screen.getByLabelText("Product creation cost"), { target: { value: "0" } });

    expect(screen.getByText("Use 1 to 1,000 points.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review & save" })).toBeDisabled();
  });

  it("marks the rule a refused save names", async () => {
    vi.mocked(updateAdminRules).mockRejectedValue(
      new AdminApiError("Starting points must be 0 or at least the minimum point sale (300).", 400, {
        errors: { "points.minimum_purchase": "Raise both in one save." },
      })
    );
    await openPage();

    fireEvent.change(screen.getByLabelText("Minimum point sale"), { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: "Review & save" }));
    fireEvent.change(dialog().getByLabelText(/Why are the rules changing/), { target: { value: "Prices" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("at least the minimum point sale (300)");
    expect(screen.getByText("Raise both in one save.")).toBeInTheDocument();
  });

  it("offers a reload when someone saved first", async () => {
    vi.mocked(updateAdminRules).mockRejectedValue(
      new AdminApiError("Someone changed these rules after you opened the page. Reload to see their values.", 409, {
        current: { "product.creation_cost": 7 },
      })
    );
    await openPage();

    fireEvent.change(screen.getByLabelText("Product creation cost"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Review & save" }));
    fireEvent.change(dialog().getByLabelText(/Why are the rules changing/), { target: { value: "Prices" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Someone changed these rules");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    });
    expect(getAdminRules).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText("Product creation cost")).toHaveValue(5);
  });

  it("shows viewers the values without inputs", async () => {
    auth.user = { is_superuser: false, permissions: ["rules.view"] };
    vi.mocked(getAdminRules).mockResolvedValue(rules({ can_manage: false }));
    await openPage();

    expect(screen.getByText("100 points")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.getByText(/Changing them needs/)).toBeInTheDocument();
  });

  it("shows the access notice without asking the server", async () => {
    auth.user = { is_superuser: false, permissions: ["reports.view"] };
    await openPage();

    expect(screen.getByText("Insufficient Permissions")).toBeInTheDocument();
    expect(getAdminRules).not.toHaveBeenCalled();
  });
});
