"use client";

import React from "react";
import { Category } from "@/lib/types";

interface CategorySidebarProps {
  categories: Category[];
  activeCategory: string;
  onSelectCategory: (slug: string) => void;
}

const DEFAULT_ICONS: Record<string, string> = {
  clothing: "checkroom",
  electronics: "devices",
  shoes: "roller_skating",
  watches: "watch",
  jewellery: "diamond",
  "health-and-beauty": "spa",
  "kids-and-babies": "child_friendly",
  sports: "sports_soccer",
  "home-and-garden": "yard",
};

export default function CategorySidebar({
  categories,
  activeCategory,
  onSelectCategory,
}: CategorySidebarProps) {
  return (
    <div className="bg-surface rounded-lg border border-line overflow-hidden shadow-sm transition-colors duration-200">
      {/* Accent Header as in Reference Image */}
      <div className="bg-accent px-4 py-3 flex items-center gap-2.5 text-on-accent font-bold uppercase tracking-wider text-sm shadow-xs">
        <span className="material-symbols-outlined text-[20px]">menu</span>
        <span>CATEGORIES</span>
      </div>

      {/* Category List Items */}
      <ul className="divide-y divide-line-subtle text-sm text-ink-body">
        <li>
          <button
            onClick={() => onSelectCategory("all")}
            className={`w-full group flex items-center justify-between px-4 py-2.5 transition-colors cursor-pointer text-left ${
              activeCategory === "all"
                ? "bg-surface-alt text-primary font-semibold border-l-4 border-primary"
                : "hover:bg-surface-alt hover:text-primary"
            }`}
          >
            <span className="flex items-center gap-3">
              <span
                className={`material-symbols-outlined text-[18px] transition-colors ${
                  activeCategory === "all" ? "text-primary" : "text-ink-muted group-hover:text-primary"
                }`}
              >
                storefront
              </span>
              <span>All Products</span>
            </span>
            <span className="material-symbols-outlined text-[16px] text-ink-muted group-hover:translate-x-0.5 transition-transform">
              chevron_right
            </span>
          </button>
        </li>

        {categories.map((cat) => {
          const isActive = activeCategory === cat.slug;
          const icon = cat.icon || DEFAULT_ICONS[cat.slug] || "category";

          return (
            <li key={cat.id}>
              <button
                onClick={() => onSelectCategory(cat.slug)}
                className={`w-full group flex items-center justify-between px-4 py-2.5 transition-colors cursor-pointer text-left ${
                  isActive
                    ? "bg-surface-alt text-primary font-semibold border-l-4 border-primary"
                    : "hover:bg-surface-alt hover:text-primary"
                }`}
              >
                <span className="flex items-center gap-3">
                  <span
                    className={`material-symbols-outlined text-[18px] transition-colors ${
                      isActive ? "text-primary" : "text-ink-muted group-hover:text-primary"
                    }`}
                  >
                    {icon}
                  </span>
                  <span>{cat.name}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  {cat.products_count !== undefined && cat.products_count > 0 && (
                    <span className="text-[11px] text-ink-muted bg-surface-sunken px-1.5 py-0.5 rounded-full">
                      {cat.products_count}
                    </span>
                  )}
                  <span className="material-symbols-outlined text-[16px] text-ink-muted group-hover:translate-x-0.5 transition-transform">
                    chevron_right
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
