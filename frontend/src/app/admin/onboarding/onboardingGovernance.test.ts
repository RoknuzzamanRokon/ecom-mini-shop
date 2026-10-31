import { describe, expect, it } from "vitest";

import { getAccessibleNavItems } from "@/lib/admin-navigation";
import type { AuthUser } from "@/lib/types";

import { canReviewOnboarding } from "./onboardingGovernance";

function staff(permissions: string[], is_superuser = false): AuthUser {
  return {
    id: 1,
    username: "staff",
    email: "",
    phone: null,
    first_name: "",
    last_name: "",
    is_staff: true,
    is_superuser,
    roles: [],
    permissions,
  };
}

/** What ADMINISTRATOR holds of the four approval steps. */
const EVERY_STEP = ["sellers.approve", "shops.approve", "products.approve", "products.publish"];

describe("canReviewOnboarding (CanApproveOnboarding)", () => {
  it("needs every approval step, as one approval runs them all", () => {
    expect(canReviewOnboarding(staff(EVERY_STEP))).toBe(true);
    for (const missing of EVERY_STEP) {
      expect(canReviewOnboarding(staff(EVERY_STEP.filter((code) => code !== missing)))).toBe(false);
    }
  });

  it("takes the admin.manage codes in place of the narrow ones", () => {
    expect(
      canReviewOnboarding(staff(["sellers.admin.manage", "shops.admin.manage", "products.admin.manage"]))
    ).toBe(true);
  });

  it("lets superusers and wildcard holders in, and nobody signed out", () => {
    expect(canReviewOnboarding(staff([], true))).toBe(true);
    expect(canReviewOnboarding(staff(["*"]))).toBe(true);
    expect(canReviewOnboarding(null)).toBe(false);
  });

  it("shows the Onboarding menu entry only to someone who can approve", () => {
    const hrefs = (user: AuthUser) => getAccessibleNavItems(user).map((item) => item.href);
    expect(hrefs(staff(EVERY_STEP))).toContain("/admin/onboarding");
    // A Sales Manager approves sellers, but not shops or products.
    expect(hrefs(staff(["sellers.approve", "sellers.view"]))).not.toContain("/admin/onboarding");
  });
});
