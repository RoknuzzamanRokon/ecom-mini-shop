import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CartItem, Product } from "@/lib/types";
import { axeViolations } from "@/test/axe";

import CartDrawer from "./CartDrawer";

const cart = vi.hoisted(() => ({
  items: [] as CartItem[],
  isCartOpen: true,
  setIsCartOpen: vi.fn(),
  removeFromCart: vi.fn(),
  increaseQuantity: vi.fn(),
  decreaseQuantity: vi.fn(),
  clearCart: vi.fn(),
  totalItemsCount: 2,
  totalAmount: 200,
  hasUnavailableItems: false,
  isLoading: false,
  isMutating: false,
  error: null as string | null,
  clearError: vi.fn(),
}));

vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/CartContext", () => ({ useCart: () => cart, maxCartQuantity: () => 99 }));

const LAMP = { id: 1, name: "Desk Lamp", slug: "desk-lamp", price: "100.00", stock: 5 } as Product;

beforeEach(() => {
  cart.items = [{ id: 11, product: LAMP, quantity: 2, subtotal: 200, is_available: true }];
  cart.isCartOpen = true;
  cart.error = "Only 2 left in stock.";
  cart.setIsCartOpen.mockReset();
  cart.removeFromCart.mockReset();
});

describe("CartDrawer (BUG-094)", () => {
  it("is a named dialog whose icon buttons say what they do", async () => {
    render(<CartDrawer />);

    expect(screen.getByRole("dialog", { name: "Shopping Cart (2)" })).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Close cart" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Desk Lamp from cart" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decrease quantity of Desk Lamp" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Increase quantity of Desk Lamp" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss message" })).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("moves focus inside and closes on Escape", async () => {
    const user = userEvent.setup();
    render(<CartDrawer />);

    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");

    expect(cart.setIsCartOpen).toHaveBeenCalledWith(false);
  });

  it("renders nothing while closed", () => {
    cart.isCartOpen = false;
    render(<CartDrawer />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
