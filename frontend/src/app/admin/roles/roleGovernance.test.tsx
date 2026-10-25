import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RoleForm } from "./roleGovernance";

vi.mock("next/link", () => import("@/test/next-link"));

function renderForm(permissionLock: string | null) {
  render(
    <RoleForm
      values={{ code: "FINANCE_DESK", name: "Finance desk", description: "", is_active: false, permissions: [] }}
      onChange={() => {}}
      onSubmit={() => {}}
      onCancel={() => {}}
      submitting={false}
      submitLabel="Save"
      error={null}
      mode="edit"
      catalog={null}
      permissionLock={permissionLock}
      idPrefix="role"
    />
  );
  return screen.getByRole("checkbox", { name: /Active/ });
}

describe("RoleForm Active checkbox (BUG-101)", () => {
  it("is locked with the permissions, since switching the role changes them for every holder", () => {
    expect(renderForm("This role grants permissions you do not hold.")).toBeDisabled();
  });

  it("is editable when the permissions are", () => {
    expect(renderForm(null)).toBeEnabled();
  });
});
