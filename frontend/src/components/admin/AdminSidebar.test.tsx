import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminSidebar from "./AdminSidebar";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { is_superuser: true } }) }));

function setViewport(desktop: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: desktop,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
}

const sidebar = () => screen.getByRole("complementary", { hidden: true, name: "Management navigation" });

beforeEach(() => {
  setViewport(false);
});

describe("Console sidebar (BUG-094)", () => {
  it("is inert while closed off screen on a phone, so Tab never lands in it", () => {
    render(<AdminSidebar isOpen={false} onClose={() => {}} />);
    expect(sidebar()).toHaveAttribute("inert");
  });

  it("is usable when opened, and Escape closes it", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<AdminSidebar isOpen onClose={onClose} />);
    expect(sidebar()).not.toHaveAttribute("inert");

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("is never inert on a desktop, where it is always on screen", () => {
    setViewport(true);
    render(<AdminSidebar isOpen={false} onClose={() => {}} />);
    expect(sidebar()).not.toHaveAttribute("inert");
  });
});
