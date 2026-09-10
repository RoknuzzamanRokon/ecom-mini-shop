"use client";

import React, { useState } from "react";
import { Product } from "@/lib/types";
import ProductCard from "./ProductCard";

interface ProductGridProps {
  products: Product[];
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
  loading?: boolean;
}

export default function ProductGrid({
  products,
  selectedCategory,
  onSelectCategory,
  loading = false,
}: ProductGridProps) {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const filterTabs = [
    { label: "All", slug: "all" },
    { label: "Clothing", slug: "clothing" },
    { label: "Electronics", slug: "electronics" },
    { label: "Shoes", slug: "shoes" },
  ];

  return (
    <div id="products-section" className="flex flex-col gap-4">
      {/* Section Header Bar with Category Filter Tabs (Reference Style) */}
      <div className="bg-surface rounded-lg border border-line px-4 py-3 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors duration-200">
        <div className="flex items-center gap-3">
          <h3 className="font-bold text-sm uppercase tracking-wider text-ink">
            NEW PRODUCTS
          </h3>
        </div>

        {/* Category Filter Tabs and Grid Toggle Controls */}
        <div className="flex items-center justify-between sm:justify-end gap-4 text-xs font-medium text-ink-muted">
          <div className="flex items-center gap-3">
            {filterTabs.map((tab) => {
              const isActive = selectedCategory === tab.slug;
              return (
                <button
                  key={tab.slug}
                  onClick={() => onSelectCategory(tab.slug)}
                  className={`pb-0.5 transition-colors cursor-pointer ${
                    isActive
                      ? "text-primary font-bold border-b-2 border-primary"
                      : "hover:text-primary"
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Grid Controls */}
          <div className="flex items-center gap-1 pl-3 border-l border-line text-ink-muted">
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1 rounded transition-colors cursor-pointer ${
                viewMode === "grid"
                  ? "bg-surface-sunken text-ink"
                  : "hover:bg-surface-alt hover:text-ink"
              }`}
              title="Grid View"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px] block">grid_view</span>
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`p-1 rounded transition-colors cursor-pointer ${
                viewMode === "list"
                  ? "bg-surface-sunken text-ink"
                  : "hover:bg-surface-alt hover:text-ink"
              }`}
              title="List View"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px] block">view_list</span>
            </button>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="py-12 flex justify-center items-center text-ink-muted">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      )}

      {/* Empty state */}
      {!loading && products.length === 0 && (
        <div className="bg-surface rounded-lg border border-line p-12 text-center text-ink-muted">
          <span className="material-symbols-outlined text-[48px] text-ink-muted/50 mb-2">
            search_off
          </span>
          <p className="text-sm font-medium">No products found for the selected filter.</p>
          <button
            onClick={() => onSelectCategory("all")}
            className="mt-3 text-xs font-semibold text-primary underline"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Product Display */}
      {!loading && products.length > 0 && (
        <div
          className={
            viewMode === "grid"
              ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
              : "flex flex-col gap-3"
          }
        >
          {products.map((product) => (
            <ProductCard key={product.id} product={product} viewMode={viewMode} />
          ))}
        </div>
      )}
    </div>
  );
}
