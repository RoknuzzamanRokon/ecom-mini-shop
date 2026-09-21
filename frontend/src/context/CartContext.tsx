"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
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

  // Initial load: check auth or restore localStorage
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      refreshCart();
    } else {
      try {
        const saved = localStorage.getItem("minishop-cart");
        if (saved) {
          const parsed = JSON.parse(saved);
          setItems(parsed);
        }
      } catch {}
    }
    setMounted(true);
  }, [refreshCart]);

  // Save guest cart changes to localStorage
  useEffect(() => {
    if (mounted && !getAuthToken()) {
      try {
        localStorage.setItem("minishop-cart", JSON.stringify(items));
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
