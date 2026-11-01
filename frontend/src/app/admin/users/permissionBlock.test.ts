import { describe, expect, it } from "vitest";

import type { AdminUserDetail } from "@/lib/admin-api";
import type { AuthUser } from "@/lib/types";

import { getPermissionBlockLock } from "./userGovernance";

function actor(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 1,
    username: "admin",
    email: "",
    phone: null,
    first_name: "",
    last_name: "",
    is_staff: true,
    is_superuser: false,
    roles: ["ADMINISTRATOR"],
    permissions: ["users.admin.view", "users.admin.manage"],
    ...overrides,
  };
}

function target(overrides: Partial<AdminUserDetail> = {}): AdminUserDetail {
  return {
    id: 2,
    username: "sales",
    email: "",
    first_name: "",
    last_name: "",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    roles: ["SALES_TEAM"],
    permissions: ["sellers.onboard", "onboarding.products.view"],
    turned_off_permissions: [],
    has_full_platform_access: false,
    customer_profile: null,
    seller_profile: null,
    date_joined: "2026-10-01T00:00:00Z",
    last_login: null,
    ...overrides,
  };
}

describe("getPermissionBlockLock", () => {
  it("lets an administrator limit a Sales Team member, whose codes they need not hold", () => {
    expect(getPermissionBlockLock(actor(), target())).toBeNull();
  });

  it("protects oneself, protected roles, superusers and full access", () => {
    expect(getPermissionBlockLock(actor(), target({ id: 1 }))).toMatch("your own");
    expect(getPermissionBlockLock(actor(), target({ roles: ["ADMINISTRATOR"] }))).toMatch("protected role");
    expect(getPermissionBlockLock(actor(), target({ is_superuser: true }))).toMatch("superuser");
    expect(
      getPermissionBlockLock(actor({ roles: ["SUPER_ADMINISTRATOR"], permissions: ["*"] }), target({ has_full_platform_access: true }))
    ).toMatch("Full platform access");
    expect(getPermissionBlockLock(actor({ permissions: ["users.admin.view"] }), target())).toMatch("users.admin.manage");
  });
});
