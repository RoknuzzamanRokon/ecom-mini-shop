"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { CartItem, Product, BackendCart } from "@/lib/types";
import {
  getCart,
  addToCartApi,
  updateCartItemApi,
  removeCartItemApi,
  clearCartApi,
} from "@/lib/api";
// Phase 2J: the byte-identical copy of this reader that used to live below is
// gone; the three legacy access-token keys are resolved in one place now.
import { getAuthToken } from "@/lib/auth";
import { useAuth } from "@/context/AuthContext";

// Items added while logged out live only in this browser under this key.
const GUEST_CART_KEY = "minishop-cart";

interface CartContextType {
  items: CartItem[];
  addToCart: (product: Product, quantity?: number) => Promise<void>;
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
  refreshCart: () => Promise<void>;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [hasUnavailableItems, setHasUnavailableItems] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  // null until auth has resolved once, then the last auth state we acted on.
  const wasAuthenticated = useRef<boolean | null>(null);

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

  // Moves the logged-out cart into the account's server cart, one POST per
  // item (the server adds to any quantity already there), then drops the local
  // copy. Checkout orders from the server cart only, so without this a login
  // mid-session left the page showing items the server had never seen.
  const mergeGuestCart = useCallback(async (token: string) => {
    let guestItems: CartItem[] = [];
    try {
      const saved = JSON.parse(localStorage.getItem(GUEST_CART_KEY) || "[]");
      if (Array.isArray(saved)) guestItems = saved;
    } catch {}
    for (const item of guestItems) {
      if (!item?.product?.id || !(item.quantity > 0)) continue;
      try {
        await addToCartApi(item.product.id, item.quantity, token);
      } catch (err) {
        // e.g. the product is no longer for sale; skip it rather than block login.
        console.warn(`Could not move "${item.product.name}" into your cart:`, err);
      }
    }
    try {
      localStorage.removeItem(GUEST_CART_KEY);
    } catch {}
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
      try {
        const saved = localStorage.getItem(GUEST_CART_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          setItems(parsed);
        }
      } catch {}
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
    if (isAuthenticated) {
      setIsLoading(true);
    } else {
      setItems([]);
      setHasUnavailableItems(false);
    }
  }

  // Save guest cart changes to localStorage
  useEffect(() => {
    if (mounted && !getAuthToken()) {
      try {
        localStorage.setItem(GUEST_CART_KEY, JSON.stringify(items));
      } catch {}
    }
  }, [items, mounted]);

  const addToCart = async (product: Product, quantity: number = 1) => {
    const token = getAuthToken();
    if (token) {
      try {
        setIsLoading(true);
        const updatedCart = await addToCartApi(product.id, quantity, token);
        applyBackendCart(updatedCart);
        setIsCartOpen(true);
        return;
      } catch (err) {
        console.warn("Backend add to cart failed, falling back to local state:", err);
      } finally {
        setIsLoading(false);
      }
    }

    // Guest / fallback mode
    setItems((prev) => {
      const existing = prev.find((item) => item.product.id === product.id);
      const price = typeof product.price === "string" ? parseFloat(product.price) : product.price;

      if (existing) {
        return prev.map((item) => {
          if (item.product.id === product.id) {
            const newQty = item.quantity + quantity;
            return {
              ...item,
              quantity: newQty,
              subtotal: price * newQty,
            };
          }
          return item;
        });
      }

      return [
        ...prev,
        {
          product,
          quantity,
          subtotal: price * quantity,
          is_available: true,
        },
      ];
    });
    setIsCartOpen(true);
  };

  const removeFromCart = async (productId: number) => {
    const token = getAuthToken();
    const item = items.find((i) => i.product.id === productId);

    if (token && item?.id) {
      try {
        setIsLoading(true);
        const updatedCart = await removeCartItemApi(item.id, token);
        applyBackendCart(updatedCart);
        return;
      } catch (err) {
        console.warn("Backend remove item failed, falling back to local state:", err);
      } finally {
        setIsLoading(false);
      }
    }

    // Guest / fallback mode
    setItems((prev) => prev.filter((item) => item.product.id !== productId));
  };

  const increaseQuantity = async (productId: number) => {
    const token = getAuthToken();
    const item = items.find((i) => i.product.id === productId);

    if (token && item?.id) {
      try {
        setIsLoading(true);
        const updatedCart = await updateCartItemApi(item.id, item.quantity + 1, token);
        applyBackendCart(updatedCart);
        return;
      } catch (err) {
        console.warn("Backend increase quantity failed, falling back to local state:", err);
      } finally {
        setIsLoading(false);
      }
    }

    // Guest / fallback mode
    setItems((prev) =>
      prev.map((item) => {
        if (item.product.id === productId) {
          const price =
            typeof item.product.price === "string"
              ? parseFloat(item.product.price)
              : item.product.price;
          const newQty = item.quantity + 1;
          return {
            ...item,
            quantity: newQty,
            subtotal: price * newQty,
          };
        }
        return item;
      })
    );
  };

  const decreaseQuantity = async (productId: number) => {
    const token = getAuthToken();
    const item = items.find((i) => i.product.id === productId);

    if (token && item?.id) {
      try {
        setIsLoading(true);
        if (item.quantity > 1) {
          const updatedCart = await updateCartItemApi(item.id, item.quantity - 1, token);
          applyBackendCart(updatedCart);
        } else {
          const updatedCart = await removeCartItemApi(item.id, token);
          applyBackendCart(updatedCart);
        }
        return;
      } catch (err) {
        console.warn("Backend decrease quantity failed, falling back to local state:", err);
      } finally {
        setIsLoading(false);
      }
    }

    // Guest / fallback mode
    setItems((prev) =>
      prev
        .map((item) => {
          if (item.product.id === productId) {
            const price =
              typeof item.product.price === "string"
                ? parseFloat(item.product.price)
                : item.product.price;
            const newQty = item.quantity - 1;
            return {
              ...item,
              quantity: newQty,
              subtotal: price * newQty,
            };
          }
          return item;
        })
        .filter((item) => item.quantity > 0)
    );
  };

  const clearCart = async () => {
    const token = getAuthToken();
    if (token) {
      try {
        setIsLoading(true);
        await clearCartApi(token);
        setItems([]);
        setHasUnavailableItems(false);
        return;
      } catch (err) {
        console.warn("Backend clear cart failed, falling back to local state:", err);
      } finally {
        setIsLoading(false);
      }
    }

    // Guest / fallback mode
    setItems([]);
    setHasUnavailableItems(false);
  };

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
