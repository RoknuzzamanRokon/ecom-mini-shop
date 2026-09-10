"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { CartItem, Product } from "@/lib/types";

interface CartContextType {
  items: CartItem[];
  addToCart: (product: Product, quantity?: number) => void;
  removeFromCart: (productId: number) => void;
  increaseQuantity: (productId: number) => void;
  decreaseQuantity: (productId: number) => void;
  clearCart: () => void;
  isCartOpen: boolean;
  setIsCartOpen: (open: boolean) => void;
  totalItemsCount: number;
  totalAmount: number;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("minishop-cart");
      if (saved) {
        setItems(JSON.parse(saved));
      }
    } catch {}
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) {
      try {
        localStorage.setItem("minishop-cart", JSON.stringify(items));
      } catch {}
    }
  }, [items, mounted]);

  const addToCart = (product: Product, quantity: number = 1) => {
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
        },
      ];
    });
    setIsCartOpen(true);
  };

  const removeFromCart = (productId: number) => {
    setItems((prev) => prev.filter((item) => item.product.id !== productId));
  };

  const increaseQuantity = (productId: number) => {
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

  const decreaseQuantity = (productId: number) => {
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

  const clearCart = () => {
    setItems([]);
  };

  const totalItemsCount = items.reduce((sum, item) => sum + item.quantity, 0);
  const totalAmount = items.reduce((sum, item) => sum + item.subtotal, 0);

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
