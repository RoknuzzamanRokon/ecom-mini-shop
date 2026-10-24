import { act, renderHook, waitFor, type RenderHookResult } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CartApiError, addToCartApi, getCart, updateCartItemApi } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { BackendCart, Product } from "@/lib/types";

import { CartProvider, useCart } from "./CartContext";

const auth = vi.hoisted(() => ({ isAuthenticated: false, isLoading: false }));

vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getCart: vi.fn(),
  addToCartApi: vi.fn(),
  updateCartItemApi: vi.fn(),
  removeCartItemApi: vi.fn(),
  clearCartApi: vi.fn(),
}));

const GUEST_CART_KEY = "minishop-cart";

function product(id: number, overrides: Partial<Product> = {}): Product {
  return {
    id,
    name: `Product ${id}`,
    slug: `product-${id}`,
    description: "",
    price: "100.00",
    stock: 10,
    is_active: true,
    in_stock: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** A server cart holding [product, quantity] lines; line ids are 100 + product id. */
function serverCart(...lines: [Product, number][]): BackendCart {
  return {
    id: 1,
    items: lines.map(([item, quantity]) => ({
      id: 100 + item.id,
      product: item,
      quantity,
      unit_price: "100.00",
      line_total: (100 * quantity).toFixed(2),
      is_available: true,
      unavailable_reason: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    })),
    total_items_count: lines.reduce((sum, [, quantity]) => sum + quantity, 0),
    total_amount: "0.00",
    has_unavailable_items: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

let hook: RenderHookResult<ReturnType<typeof useCart>, unknown>;

/** The cart as the provider currently exposes it. */
const cart = () => hook.result.current;

function renderCart() {
  hook = renderHook(useCart, { wrapper: CartProvider });
  return hook;
}

async function renderSignedIn(initial: BackendCart) {
  setTokens("access", "refresh");
  auth.isAuthenticated = true;
  vi.mocked(getCart).mockResolvedValue(initial);
  const view = renderCart();
  await waitFor(() => expect(cart().isLoading).toBe(false));
  expect(cart().items).toHaveLength(initial.items.length);
  return view;
}

function savedGuestIds(): number[] {
  const saved = JSON.parse(localStorage.getItem(GUEST_CART_KEY) ?? "[]");
  return saved.map((line: { product: Product }) => line.product.id);
}

const quantities = () => cart().items.map((item) => [item.product.id, item.quantity]);

beforeEach(() => {
  vi.resetAllMocks();
  auth.isAuthenticated = false;
  auth.isLoading = false;
});

describe("CartContext, signed in", () => {
  it("keeps the server's cart and shows why when an add is refused", async () => {
    const kept = product(1);
    await renderSignedIn(serverCart([kept, 1]));
    vi.mocked(addToCartApi).mockRejectedValue(new CartApiError("Only 2 left in stock.", 400));

    let added: boolean | undefined;
    await act(async () => {
      added = await cart().addToCart(product(2), 3);
    });

    expect(added).toBe(false);
    expect(cart().error).toBe("Only 2 left in stock.");
    expect(quantities()).toEqual([[1, 1]]);
    // The cart shown was re-read from the server after the failure.
    expect(getCart).toHaveBeenCalledTimes(2);
    // The drawer opens to show the refusal.
    expect(cart().isCartOpen).toBe(true);
  });

  it("shows a generic message and the server's quantity when an update fails without a reason", async () => {
    const item = product(1);
    await renderSignedIn(serverCart([item, 1]));
    vi.mocked(updateCartItemApi).mockRejectedValue(new Error(""));

    await act(() => cart().increaseQuantity(1));

    expect(updateCartItemApi).toHaveBeenCalledWith(101, 2, "access");
    expect(cart().error).toBe("Could not update your cart.");
    expect(quantities()).toEqual([[1, 1]]);
    expect(cart().isMutating).toBe(false);
  });

  it("drops a second change while the first is still on its way", async () => {
    const item = product(1);
    await renderSignedIn(serverCart([item, 1]));
    let finish!: (value: BackendCart) => void;
    vi.mocked(updateCartItemApi).mockReturnValue(new Promise((resolve) => (finish = resolve)));

    let first!: Promise<void>;
    act(() => {
      first = cart().increaseQuantity(1);
    });
    await waitFor(() => expect(cart().isMutating).toBe(true));
    await act(() => cart().increaseQuantity(1));
    expect(updateCartItemApi).toHaveBeenCalledTimes(1);

    await act(async () => {
      finish(serverCart([item, 2]));
      await first;
    });
    expect(quantities()).toEqual([[1, 2]]);
    expect(cart().error).toBeNull();
  });

  it("clears the error when the next change succeeds", async () => {
    const item = product(1);
    await renderSignedIn(serverCart([item, 1]));
    vi.mocked(updateCartItemApi)
      .mockRejectedValueOnce(new CartApiError("Not enough stock.", 400))
      .mockResolvedValueOnce(serverCart([item, 2]));

    await act(() => cart().increaseQuantity(1));
    expect(cart().error).toBe("Not enough stock.");
    await act(() => cart().increaseQuantity(1));

    expect(cart().error).toBeNull();
    expect(quantities()).toEqual([[1, 2]]);
  });
});

describe("CartContext, guest cart", () => {
  it("refuses more than the product's stock and says so", async () => {
    renderCart();
    const scarce = product(1, { stock: 2 });

    let added: boolean | undefined;
    await act(async () => {
      added = await cart().addToCart(scarce, 3);
    });

    expect(added).toBe(false);
    expect(cart().error).toBe('You can have at most 2 of "Product 1" in your cart.');
    expect(cart().items).toEqual([]);
    expect(localStorage.getItem(GUEST_CART_KEY)).toBeNull();
  });

  it("on login moves each line once, names refused ones and keeps lines that hit an outage", async () => {
    const [moved, refused, delayed] = [product(1), product(2), product(3)];
    localStorage.setItem(
      GUEST_CART_KEY,
      JSON.stringify([moved, refused, delayed].map((item) => ({ product: item, quantity: 1, subtotal: 100 })))
    );
    const view = renderCart();
    expect(cart().items).toHaveLength(3);

    const savedAtEachCall: number[][] = [];
    vi.mocked(addToCartApi).mockImplementation(async (productId) => {
      savedAtEachCall.push(savedGuestIds());
      if (productId === refused.id) throw new CartApiError("This product is not for sale.", 400);
      if (productId === delayed.id) throw new CartApiError("Service unavailable", 503);
      return serverCart([moved, 1]);
    });
    vi.mocked(getCart).mockResolvedValue(serverCart([moved, 1]));
    setTokens("access", "refresh");
    auth.isAuthenticated = true;
    view.rerender();
    await waitFor(() => expect(getCart).toHaveBeenCalled());
    await waitFor(() => expect(cart().isLoading).toBe(false));

    expect(addToCartApi).toHaveBeenCalledTimes(3);
    expect(quantities()).toEqual([[1, 1]]);
    expect(cart().error).toContain("Could not move Product 2 from your guest cart");
    expect(cart().error).toContain("1 item(s) from your guest cart could not be moved yet");
    expect(savedGuestIds()).toEqual([delayed.id]);
    // A line leaves the saved guest cart as soon as it is handled, so a run
    // interrupted part-way never moves it twice.
    expect(savedAtEachCall).toEqual([[1, 2, 3], [2, 3], [3]]);
  });
});
