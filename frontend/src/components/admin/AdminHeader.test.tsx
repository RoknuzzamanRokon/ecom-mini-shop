import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@/test/axe";

import AdminHeader from "./AdminHeader";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/components/notifications/NotificationBell", () => ({ default: () => null }));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "ops", first_name: "Rina", last_name: "Das", email: "rina@example.com", roles: ["ADMINISTRATOR"] },
    logout: vi.fn(),
  }),
}));

const menuButton = () => screen.getByRole("button", { name: "Account menu for Rina Das" });

describe("Console account menu (BUG-094)", () => {
  it("says whether it is open and which element it controls", async () => {
    const user = userEvent.setup();
    render(<AdminHeader onMenuToggle={() => {}} />);
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");

    await user.click(menuButton());

    expect(menuButton()).toHaveAttribute("aria-expanded", "true");
    const menu = document.getElementById(menuButton().getAttribute("aria-controls")!);
    expect(menu).toContainElement(screen.getByRole("link", { name: "View Profile" }));
    expect(await axeViolations()).toEqual([]);
  });

  it("closes on Escape and puts focus back on its button", async () => {
    const user = userEvent.setup();
    render(<AdminHeader onMenuToggle={() => {}} />);
    await user.click(menuButton());
    await user.tab();
    expect(screen.getByRole("link", { name: "View Profile" })).toHaveFocus();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("link", { name: "View Profile" })).not.toBeInTheDocument();
    expect(menuButton()).toHaveFocus();
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on a click outside or when Tab leaves it, not when the pointer leaves", async () => {
    const user = userEvent.setup();
    render(
      <>
        <AdminHeader onMenuToggle={() => {}} />
        <button type="button">Elsewhere</button>
      </>
    );

    await user.click(menuButton());
    fireEvent.mouseLeave(document.getElementById(menuButton().getAttribute("aria-controls")!)!);
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");

    await user.click(menuButton());
    await user.tab(); // View Profile
    await user.tab(); // Sign Out
    await user.tab(); // out of the menu
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("stays open when its plain text is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminHeader onMenuToggle={() => {}} />);
    await user.click(menuButton());

    await user.click(screen.getByText("Assigned Roles"));

    expect(menuButton()).toHaveAttribute("aria-expanded", "true");
  });
});
