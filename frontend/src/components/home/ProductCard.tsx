"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Product } from "@/lib/types";
import { useCart } from "@/context/CartContext";
import { formatImageUrl } from "@/lib/api";

interface ProductCardProps {
  product: Product;
  viewMode?: "grid" | "list";
}

export default function ProductCard({ product, viewMode = "grid" }: ProductCardProps) {
  const { addToCart } = useCart();
  const [imgSrc, setImgSrc] = useState(formatImageUrl(product.image_url || product.image));

  const badgeUpper = (product.badge || "").toUpperCase();

  const getBadgeClass = (badge: string) => {
    switch (badge) {
      case "NEW":
        return "bg-badge-new text-white";
      case "HOT":
        return "bg-badge-hot text-white";
      case "SALE":
        return "bg-accent text-on-accent";
      case "TOP":
        return "bg-badge-top text-white";
      default:
        return "bg-badge-default text-on-badge-default";
    }
  };

  if (viewMode === "list") {
    return (
      <div className="group bg-surface rounded-lg border border-line overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col sm:flex-row items-center p-2.5 gap-4">
        <div className="relative aspect-[4/3] w-28 h-24 bg-surface-alt rounded-md overflow-hidden shrink-0">
          <Image
            src={imgSrc}
            alt={product.name}
            fill
            sizes="112px"
            onError={() => setImgSrc("/placeholder.svg")}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          {badgeUpper && (
            <span
              className={`absolute top-1.5 right-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full uppercase shadow-xs ${getBadgeClass(
                badgeUpper
              )}`}
            >
              {badgeUpper}
            </span>
          )}
        </div>

        <div className="flex-1 flex flex-col justify-between w-full">
          <div>
            <div className="flex items-center gap-2 flex-wrap text-[11px]">
              <span className="text-ink-muted uppercase tracking-wider font-medium">
                {product.category?.name || "General"}
              </span>
              {product.shop && (
                <>
                  <span className="text-ink-muted">•</span>
                  <Link
                    href={`/shop/${product.shop.slug}`}
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-0.5 text-ink-muted hover:text-primary transition-colors font-medium"
                    title={`Visit ${product.shop.name}`}
                  >
                    <span className="material-symbols-outlined text-[12px]">storefront</span>
                    <span className="truncate max-w-[140px]">{product.shop.name}</span>
                  </Link>
                </>
              )}
            </div>
            <Link
              href={`/product/${product.slug}`}
              className="font-semibold text-sm text-ink hover:text-primary line-clamp-1 mt-0.5 block transition-colors"
            >
              {product.name}
            </Link>
            <p className="text-xs text-ink-body line-clamp-2 mt-0.5">{product.description}</p>
          </div>

          <div className="mt-2.5 pt-1.5 flex items-center justify-between border-t border-line">
            <div className="flex items-center gap-3">
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-base text-ink">৳{product.price}</span>
                {product.old_price && (
                  <span className="text-xs text-price-old line-through">৳{product.old_price}</span>
                )}
              </div>
              <div className="flex items-center gap-0.5 text-star">
                <span className="material-symbols-outlined fill-active text-[13px]">star</span>
                <span className="material-symbols-outlined fill-active text-[13px]">star</span>
                <span className="material-symbols-outlined fill-active text-[13px]">star</span>
                <span className="material-symbols-outlined fill-active text-[13px]">star</span>
                <span className="material-symbols-outlined fill-active text-[13px]">star</span>
              </div>
            </div>

            <button
              onClick={() => addToCart(product, 1)}
              className="bg-primary hover:bg-primary-hover text-on-primary px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs cursor-pointer"
              title="Add to Cart"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">add_shopping_cart</span>
              <span>Add to Cart</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group bg-surface rounded-lg border border-line overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col">
      {/* Thumbnail - Shorter aspect ratio (4/3) for compact card */}
      <div className="relative aspect-[4/3] w-full bg-surface-alt overflow-hidden">
        <Image
          src={imgSrc}
          alt={product.name}
          fill
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
          onError={() => setImgSrc("/placeholder.svg")}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
        />
        {badgeUpper && (
          <span
            className={`absolute top-2 right-2 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase shadow-xs ${getBadgeClass(
              badgeUpper
            )}`}
          >
            {badgeUpper}
          </span>
        )}
      </div>

      {/* Content - Compact padding */}
      <div className="p-3 flex flex-col flex-1">
        <div className="flex items-center justify-between gap-1 text-[11px] mb-0.5">
          <span className="text-ink-muted uppercase tracking-wider font-medium truncate">
            {product.category?.name || "General"}
          </span>
          {product.shop && (
            <Link
              href={`/shop/${product.shop.slug}`}
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-0.5 text-ink-muted hover:text-primary transition-colors font-medium shrink-0 max-w-[55%]"
              title={`Visit ${product.shop.name}`}
            >
              <span className="material-symbols-outlined text-[12px]">storefront</span>
              <span className="truncate">{product.shop.name}</span>
            </Link>
          )}
        </div>
        <Link
          href={`/product/${product.slug}`}
          className="font-semibold text-xs text-ink hover:text-primary line-clamp-1 mt-0.5 transition-colors"
        >
          {product.name}
        </Link>

        {/* Stars Rating */}
        <div className="flex items-center gap-0.5 text-star my-1">
          <span className="material-symbols-outlined fill-active text-[13px]">star</span>
          <span className="material-symbols-outlined fill-active text-[13px]">star</span>
          <span className="material-symbols-outlined fill-active text-[13px]">star</span>
          <span className="material-symbols-outlined fill-active text-[13px]">star</span>
          <span className="material-symbols-outlined fill-active text-[13px]">star</span>
        </div>

        {/* Price & Action */}
        <div className="mt-auto pt-1.5 flex items-center justify-between border-t border-line">
          <div className="flex items-baseline gap-1.5">
            <span className="font-bold text-sm text-ink">৳{product.price}</span>
            {product.old_price && (
              <span className="text-[11px] text-price-old line-through">৳{product.old_price}</span>
            )}
          </div>
          <button
            onClick={() => addToCart(product, 1)}
            className="bg-primary hover:bg-primary-hover text-on-primary p-1.5 rounded-md transition-colors shadow-xs cursor-pointer active:scale-95"
            title="Add to Cart"
            type="button"
          >
            <span className="material-symbols-outlined text-[16px] block">add_shopping_cart</span>
          </button>
        </div>
      </div>
    </div>
  );
}
