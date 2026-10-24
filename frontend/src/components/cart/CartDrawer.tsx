"use client";

import React, { useId } from "react";
import Image from "next/image";
import Link from "next/link";
import { Dialog } from "@/components/feedback";
import { maxCartQuantity, useCart } from "@/context/CartContext";
import { formatImageUrl } from "@/lib/api";

export default function CartDrawer() {
  const {
    items,
    isCartOpen,
    setIsCartOpen,
    removeFromCart,
    increaseQuantity,
    decreaseQuantity,
    clearCart,
    totalItemsCount,
    totalAmount,
    hasUnavailableItems,
    isLoading,
    isMutating,
    error,
    clearError,
  } = useCart();
  const titleId = useId();

  // Each change waits for the previous one, so a quantity is never computed
  // from a cart the server has already moved past.
  const busy = isLoading || isMutating;

  // A labelled modal drawer: Escape or the backdrop closes it, focus stays
  // inside while open and returns to the cart button after (BUG-094).
  return (
    <Dialog
      open={isCartOpen}
      onClose={() => setIsCartOpen(false)}
      labelledBy={titleId}
      placement="right"
      className="w-full max-w-md bg-surface h-full shadow-2xl flex flex-col border-l border-line transition-colors duration-200"
    >
      {/* Header */}
      <div className="p-4 border-b border-line flex items-center justify-between bg-surface-alt/50">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="material-symbols-outlined text-primary text-[22px]">
            shopping_bag
          </span>
          <h2 id={titleId} className="font-bold text-sm uppercase tracking-wider text-ink">
            Shopping Cart ({totalItemsCount})
          </h2>
        </div>
        <button
          onClick={() => setIsCartOpen(false)}
          className="w-8 h-8 rounded-full hover:bg-surface-sunken flex items-center justify-center text-ink-muted transition-colors cursor-pointer"
          type="button"
          aria-label="Close cart"
          title="Close cart"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[20px]">close</span>
        </button>
      </div>

      {/* Item List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {error && (
          <div
            role="alert"
            className="p-3 bg-danger/10 border border-danger/30 rounded-lg flex items-start gap-2.5 text-xs text-danger"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0 mt-0.5">error</span>
            <p className="flex-1">{error}</p>
            <button
              type="button"
              onClick={clearError}
              className="shrink-0 hover:opacity-80 cursor-pointer"
              aria-label="Dismiss message"
              title="Dismiss"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">close</span>
            </button>
          </div>
        )}

        {hasUnavailableItems && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-start gap-2.5 text-xs text-amber-700 dark:text-amber-400">
            <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0 mt-0.5">warning</span>
            <div>
              <p className="font-semibold">Items unavailable</p>
              <p className="text-[11px] opacity-90">Some items in your cart are no longer available for purchase and have been excluded from the total.</p>
            </div>
          </div>
        )}

        {items.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-ink-muted">
            <span aria-hidden="true" className="material-symbols-outlined text-[64px] text-ink-muted/40 mb-3">
              remove_shopping_cart
            </span>
            <p className="font-semibold text-base text-ink">Your cart is empty</p>
            <p className="text-xs text-ink-body mt-1">
              Explore our catalog and find great deals today.
            </p>
            <button
              onClick={() => setIsCartOpen(false)}
              className="mt-4 bg-primary text-on-primary text-xs font-semibold px-4 py-2 rounded-md hover:bg-primary-hover transition-colors cursor-pointer"
            >
              Continue Shopping
            </button>
          </div>
        ) : (
          items.map(({ product, quantity, subtotal, is_available, unavailable_reason }) => {
            const imgUrl = formatImageUrl(
              product.image_url ||
              (product.image ? product.image : "/placeholder.svg")
            );
            const isUnavailable = is_available === false;
            const atLimit = quantity >= maxCartQuantity(product);

            return (
              <div
                key={product.id}
                className={`flex gap-3 p-2.5 rounded-lg border transition-colors ${
                  isUnavailable
                    ? "bg-danger/5 border-danger/30 opacity-80"
                    : "bg-surface-alt/40 border-line"
                }`}
              >
                <div className="relative w-16 h-16 rounded-md overflow-hidden bg-surface-alt shrink-0 border border-line">
                  <Image
                    src={imgUrl}
                    alt={product.name}
                    fill
                    sizes="64px"
                    className="object-cover"
                  />
                </div>

                <div className="flex-1 min-w-0">
                  <h4 className="text-xs font-semibold text-ink line-clamp-1">
                    {product.name}
                  </h4>
                  <p className="text-[11px] text-ink-muted mt-0.5">
                    ৳{product.price} each
                  </p>

                  {isUnavailable && (
                    <div className="mt-1">
                      <span className="inline-block px-1.5 py-0.5 text-[10px] font-medium bg-danger/10 text-danger rounded">
                        {unavailable_reason || "Unavailable"}
                      </span>
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-2">
                    {/* Quantity Stepper */}
                    {!isUnavailable ? (
                      <div className="flex items-center border border-line rounded bg-surface overflow-hidden">
                        <button
                          onClick={() => decreaseQuantity(product.id)}
                          disabled={busy}
                          className="px-2 py-0.5 text-xs text-ink hover:bg-surface-sunken transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                          type="button"
                          aria-label={`Decrease quantity of ${product.name}`}
                          title="Decrease"
                        >
                          -
                        </button>
                        <span className="px-2.5 text-xs font-semibold text-ink">
                          {quantity}
                        </span>
                        <button
                          onClick={() => increaseQuantity(product.id)}
                          disabled={busy || atLimit}
                          className="px-2 py-0.5 text-xs text-ink hover:bg-surface-sunken transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                          type="button"
                          aria-label={`Increase quantity of ${product.name}`}
                          title={atLimit ? `At most ${maxCartQuantity(product)} per order` : "Increase"}
                        >
                          +
                        </button>
                      </div>
                    ) : (
                      <span className="text-[11px] text-ink-muted italic">Qty: {quantity}</span>
                    )}

                    <div className="flex items-center gap-3">
                      <span className={`font-bold text-xs ${isUnavailable ? "text-ink-muted line-through" : "text-primary"}`}>
                        ৳{subtotal.toFixed(2)}
                      </span>
                      <button
                        onClick={() => removeFromCart(product.id)}
                        disabled={busy}
                        className="text-danger hover:text-danger/80 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        type="button"
                        aria-label={`Remove ${product.name} from cart`}
                        title="Remove"
                      >
                        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                          delete
                        </span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Actions */}
      {items.length > 0 && (
        <div className="p-4 border-t border-line bg-surface space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-ink-body font-medium">Subtotal</span>
            <span className="text-base font-bold text-ink">
              ৳{totalAmount.toFixed(2)}
            </span>
          </div>

          <p className="text-[11px] text-ink-muted">
            Shipping & taxes calculated at checkout. Free shipping on orders over ৳99.
          </p>

          <div className="flex gap-2">
            <button
              onClick={clearCart}
              disabled={busy}
              className="px-3 py-2 text-xs font-semibold text-ink-muted hover:text-danger hover:bg-surface-sunken rounded border border-line transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              type="button"
            >
              Clear
            </button>
            <Link
              href="/checkout"
              onClick={() => setIsCartOpen(false)}
              className="flex-1 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider py-2.5 rounded shadow-sm text-center transition-colors flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Checkout</span>
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                arrow_forward
              </span>
            </Link>
          </div>
        </div>
      )}
    </Dialog>
  );
}
