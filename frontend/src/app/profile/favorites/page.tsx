"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { formatImageUrl } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useFavorites } from "@/context/FavoritesContext";

export default function FavoritesPage() {
  const { addToCart } = useCart();
  const { favorites, isLoading: loading, toggleFavorite, refresh } = useFavorites();
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const load = refresh;

  const handleRemove = async (productId: number) => {
    setRemovingId(productId);
    try {
      await toggleFavorite(productId);
    } catch {
      setError("Could not remove that item.");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-bold text-ink">Favorites</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Products you saved for later.
        </p>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            favorite
          </span>
          <p className="text-sm text-ink-body mt-2">Loading favorites…</p>
        </div>
      ) : error ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center">
          <p className="text-sm text-accent font-medium">{error}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : favorites.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[56px] text-ink-muted/40">
            favorite
          </span>
          <h2 className="text-base font-bold text-ink mt-2">No favorites yet</h2>
          <p className="text-sm text-ink-body mt-1 mb-5">
            Tap the heart on any product to save it here.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
          >
            Browse Products
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {favorites.map(({ id, product }) => (
            <div
              key={id}
              className="bg-surface rounded-2xl border border-line shadow-sm overflow-hidden flex flex-col"
            >
              <Link
                href={`/product/${product.slug}`}
                className="relative block aspect-square bg-surface-alt overflow-hidden"
              >
                <Image
                  src={formatImageUrl(product.image_url)}
                  alt={product.name}
                  fill
                  className="object-cover hover:scale-105 transition-transform duration-300"
                />
              </Link>

              <div className="p-4 flex flex-col gap-2 flex-1">
                <Link
                  href={`/product/${product.slug}`}
                  className="text-sm font-bold text-ink hover:text-primary transition-colors line-clamp-2"
                >
                  {product.name}
                </Link>

                {product.shop && (
                  <p className="flex items-center gap-1 text-[11px] text-ink-muted truncate">
                    <span className="material-symbols-outlined text-[13px]">storefront</span>
                    {product.shop.name}
                  </p>
                )}

                <div className="flex items-baseline gap-2 mt-auto pt-1">
                  <span className="text-base font-bold text-primary">৳{product.price}</span>
                  {product.old_price && (
                    <span className="text-xs text-ink-muted line-through">
                      ৳{product.old_price}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => addToCart(product, 1)}
                    disabled={product.in_stock === false}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 bg-primary hover:bg-primary-hover text-on-primary font-bold text-[11px] uppercase tracking-wider px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[15px]">
                      add_shopping_cart
                    </span>
                    {product.in_stock === false ? "Out of Stock" : "Add to Cart"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemove(product.id)}
                    disabled={removingId === product.id}
                    title="Remove from favorites"
                    className="p-2 rounded-lg border border-line text-accent hover:bg-accent/10 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
