"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { CartItem, Product, BackendCart } from "@/lib/types";
import {
  getCart,
  addToCartApi,
  updateCartItemApi,
  removeCartItemApi,
  clearCartApi,
  CartApiError,
} from "@/lib/api";
// Phase 2J: the byte-identical copy of this reader that used to live below is
// gone; the three legacy access-token keys are resolved in one place now.
import { getAuthToken } from "@/lib/auth";
import { useAuth } from "@/context/AuthContext";

// Items added while logged out live only in this browser under this key.
const GUEST_CART_KEY = "minishop-cart";

// The server's per-line cap (cart.models.CartItem.MAX_QUANTITY).
export const MAX_CART_QUANTITY = 99;

/** The most of a product one cart line can hold: its stock, within the server's cap. */
export function maxCartQuantity(product: Pick<Product, "stock">): number {
  const stock = typeof product.stock === "number" ? product.stock : MAX_CART_QUANTITY;
  return Math.max(0, Math.min(stock, MAX_CART_QUANTITY));
}

function readGuestCart(): CartItem[] {
  try {
    const saved = JSON.parse(localStorage.getItem(GUEST_CART_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

function writeGuestCart(items: CartItem[]) {
  try {
    if (items.length > 0) localStorage.setItem(GUEST_CART_KEY, JSON.stringify(items));
    else localStorage.removeItem(GUEST_CART_KEY);
  } catch {}
}

function unitPrice(product: Product): number {
  return typeof product.price === "string" ? parseFloat(product.price) : product.price;
}

interface CartContextType {
  items: CartItem[];
  /**
   * Resolves true once the item is in the cart. The drawer opens to show the
   * item or the refusal, unless `openCart: false`.
   */
  addToCart: (product: Product, quantity?: number, options?: { openCart?: boolean }) => Promise<boolean>;
  removeFromCart: (productId: number) => Promise<void>;
  increaseQuantity: (productId: number) => Promise<void>;
  decreaseQuantity: (productId: number) => Promise<void>;
  clearCart: () => Promise<void>;
  isCartOpen: boolean;
  setIsCartOpen: (open: boolean) => void;
  totalItemsCount: number;
  totalAmount: number;
  hasUnavailableItems: boolean;
  isLoading: boolean;
  /** A signed-in change is on its way to the server; steppers wait for it. */
  isMutating: boolean;
  /** Why the last cart change did not happen (the cart shown is the server's). */
  error: string | null;
  clearError: () => void;
  refreshCart: () => Promise<void>;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [hasUnavailableItems, setHasUnavailableItems] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  // null until auth has resolved once, then the last auth state we acted on.
  const wasAuthenticated = useRef<boolean | null>(null);
  // One signed-in change at a time: a second click while one is in flight is
  // dropped, so quantities are never computed from a stale cart.
  const busy = useRef(false);
  // The latest items, for handlers created by an earlier render.
  const itemsRef = useRef<CartItem[]>([]);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  const applyBackendCart = useCallback((backendCart: BackendCart) => {
    const mapped: CartItem[] = (backendCart.items || []).map((bi) => {
      const unitPrice = parseFloat(bi.unit_price) || 0;
      return {
        id: bi.id,
        product: bi.product,
        quantity: bi.quantity,
        subtotal: parseFloat(bi.line_total) || unitPrice * bi.quantity,
        is_available: bi.is_available,
        unavailable_reason: bi.unavailable_reason,
      };
    });
    setItems(mapped);
    setHasUnavailableItems(Boolean(backendCart.has_unavailable_items));
  }, []);

  const refreshCart = useCallback(async () => {
    const token = getAuthToken();
    if (!token) return;
    try {
      setIsLoading(true);
      const backendCart = await getCart(token);
      applyBackendCart(backendCart);
    } catch {
      // If token expired or fetch failed, keep current items
    } finally {
      setIsLoading(false);
    }
  }, [applyBackendCart]);

  // A signed-in change goes to the server only. On failure the local cart is
  // left alone, the error is kept for the UI and the server cart is re-read,
  // so what is shown is always what checkout will order (BUG-010).
  const mutateServerCart = useCallback(
    async (request: () => Promise<BackendCart | null>, failure: string): Promise<boolean> => {
      if (busy.current) return false;
      busy.current = true;
      setIsMutating(true);
      setError(null);
      try {
        const backendCart = await request();
        if (backendCart) {
          applyBackendCart(backendCart);
        } else {
          setItems([]);
          setHasUnavailableItems(false);
        }
        return true;
      } catch (err) {
        setError(err instanceof Error && err.message ? err.message : failure);
        await refreshCart();
        return false;
      } finally {
        busy.current = false;
        setIsMutating(false);
      }
    },
    [applyBackendCart, refreshCart]
  );

  // Moves the logged-out cart into the account's server cart, one POST per
  // item (the server adds to any quantity already there). Checkout orders from
  // the server cart only, so without this a login mid-session left the page
  // showing items the server had never seen. Each line leaves the saved copy
  // as soon as it is merged, so an interrupted run never adds it twice
  // (BUG-084). A line the server refuses is dropped and named; one that hit an
  // outage stays saved and is tried again on the next load.
  const mergeGuestCart = useCallback(async (token: string) => {
    let pending = readGuestCart();
    if (pending.length === 0) return;
    const refused: string[] = [];
    for (const item of [...pending]) {
      if (item?.product?.id && item.quantity > 0) {
        try {
          await addToCartApi(item.product.id, item.quantity, token);
        } catch (err) {
          const isRefusal =
            err instanceof CartApiError && err.status >= 400 && err.status < 500 && ![401, 408, 429].includes(err.status);
          if (!isRefusal) continue;
          refused.push(item.product.name);
        }
      }
      pending = pending.filter((other) => other !== item);
      writeGuestCart(pending);
    }
    const notes: string[] = [];
    if (refused.length > 0) {
      notes.push(`Could not move ${refused.join(", ")} from your guest cart: no longer available in that quantity.`);
    }
    if (pending.length > 0) {
      notes.push(`${pending.length} item(s) from your guest cart could not be moved yet. We will try again on your next visit.`);
    }
    if (notes.length > 0) setError(notes.join(" "));
  }, []);

  const loadAccountCart = useCallback(
    async (token: string | null) => {
      try {
        if (token) {
          await mergeGuestCart(token);
          await refreshCart();
        }
      } finally {
        setIsLoading(false);
      }
    },
    [mergeGuestCart, refreshCart]
  );

  // Initial load: restore the guest cart; a logged-in cart loads via the auth effect below
  useEffect(() => {
    if (!getAuthToken()) {
      const saved = readGuestCart();
      if (saved.length > 0) setItems(saved);
    }
    setMounted(true);
  }, []);

  // Load (and merge into) the account cart on login, including a login that
  // happens without a page reload.
  useEffect(() => {
    if (authLoading) return;
    const prev = wasAuthenticated.current;
    wasAuthenticated.current = isAuthenticated;
    if (isAuthenticated && prev !== true) {
      loadAccountCart(getAuthToken());
    }
  }, [isAuthenticated, authLoading, loadAccountCart]);

  // Adjusted during render (not in an effect) so no stale frame shows. On
  // login the cart reads as loading until the effect above has loaded it
  // (checkout waits on that). On logout the server cart stays with the
  // account, so the guest cart starts empty.
  const [cartIsAccountCart, setCartIsAccountCart] = useState(false);
  if (!authLoading && cartIsAccountCart !== isAuthenticated) {
    setCartIsAccountCart(isAuthenticated);
    setError(null);
    if (isAuthenticated) {
      setIsLoading(true);
    } else {
      setItems([]);
      setHasUnavailableItems(false);
    }
  }

  // Save guest cart changes to localStorage
  useEffect(() => {
    if (mounted && !getAuthToken()) writeGuestCart(items);
  }, [items, mounted]);

  const addToCart = async (
    product: Product,
    quantity: number = 1,
    { openCart = true }: { openCart?: boolean } = {}
  ): Promise<boolean> => {
    const token = getAuthToken();
    if (token) {
      const added = await mutateServerCart(
        () => addToCartApi(product.id, quantity, token),
        "Could not add this item to your cart."
      );
      // The drawer opens either way: it shows the item, or why it was refused.
      if (openCart) setIsCartOpen(true);
      return added;
    }

    // Guest cart: kept in this browser only.
    const limit = maxCartQuantity(product);
    const existing = itemsRef.current.find((item) => item.product.id === product.id);
    if ((existing?.quantity ?? 0) + quantity > limit) {
      setError(`You can have at most ${limit} of "${product.name}" in your cart.`);
      if (openCart) setIsCartOpen(true);
      return false;
    }
    setError(null);
    setItems((prev) => {
      const price = unitPrice(product);
      if (prev.some((item) => item.product.id === product.id)) {
        return prev.map((item) => {
          if (item.product.id !== product.id) return item;
          const newQty = item.quantity + quantity;
          return { ...item, quantity: newQty, subtotal: price * newQty };
        });
      }
      return [...prev, { product, quantity, subtotal: price * quantity, is_available: true }];
    });
    if (openCart) setIsCartOpen(true);
    return true;
  };

  /** Moves a line to `quantity` (0 removes it), on the server when signed in. */
  const setLineQuantity = async (productId: number, quantity: number) => {
    const item = itemsRef.current.find((i) => i.product.id === productId);
    if (!item) return;
    const token = getAuthToken();
    if (token) {
      const itemId = item.id;
      if (!itemId) {
        await refreshCart();
        return;
      }
      await mutateServerCart(
        () => (quantity > 0 ? updateCartItemApi(itemId, quantity, token) : removeCartItemApi(itemId, token)),
        "Could not update your cart."
      );
      return;
    }

    setError(null);
    setItems((prev) =>
      prev
        .map((line) =>
          line.product.id === productId
            ? { ...line, quantity, subtotal: unitPrice(line.product) * quantity }
            : line
        )
        .filter((line) => line.quantity > 0)
    );
  };

  const removeFromCart = (productId: number) => setLineQuantity(productId, 0);

  const increaseQuantity = async (productId: number) => {
    const item = itemsRef.current.find((i) => i.product.id === productId);
    if (!item || item.quantity >= maxCartQuantity(item.product)) return;
    await setLineQuantity(productId, item.quantity + 1);
  };

  const decreaseQuantity = async (productId: number) => {
    const item = itemsRef.current.find((i) => i.product.id === productId);
    if (!item) return;
    await setLineQuantity(productId, item.quantity - 1);
  };

  const clearCart = async () => {
    const token = getAuthToken();
    if (token) {
      await mutateServerCart(async () => {
        await clearCartApi(token);
        return null;
      }, "Could not clear your cart.");
      return;
    }

    setError(null);
    setItems([]);
    setHasUnavailableItems(false);
  };

  const clearError = useCallback(() => setError(null), []);

  // Authoritative sums: exclude unavailable items from totals
  const totalItemsCount = items.reduce(
    (sum, item) => (item.is_available !== false ? sum + item.quantity : sum),
    0
  );
  const totalAmount = items.reduce(
    (sum, item) => (item.is_available !== false ? sum + item.subtotal : sum),
    0
  );

  return (
    <CartContext.Provider
      value={{
        items,
        addToCart,
        removeFromCart,
        increaseQuantity,
        decreaseQuantity,
        clearCart,
        isCartOpen,
        setIsCartOpen,
        totalItemsCount,
        totalAmount,
        hasUnavailableItems,
        isLoading,
        isMutating,
        error,
        clearError,
        refreshCart,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error("useCart must be used within a CartProvider");
  }
  return context;
}
