"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Category } from "@/lib/types";

interface NavbarProps {
  categories?: Category[];
  activeCategory?: string;
  onSelectCategory?: (slug: string) => void;
}

export default function Navbar({
  categories = [],
  activeCategory = "all",
  onSelectCategory,
}: NavbarProps) {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const defaultNavItems = [
    { name: "Home", slug: "all" },
    { name: "Clothing", slug: "clothing" },
    { name: "Electronics", slug: "electronics" },
    { name: "Health & Beauty", slug: "health-and-beauty" },
    { name: "Home & Garden", slug: "home-and-garden" },
    { name: "Watches", slug: "watches" },
    { name: "Jewellery", slug: "jewellery" },
    { name: "Shoes", slug: "shoes" },
    { name: "Kids & Babies", slug: "kids-and-babies" },
  ];

  const items =
    categories.length > 0
      ? [{ name: "Home", slug: "all" }, ...categories.map((c) => ({ name: c.name, slug: c.slug }))]
      : defaultNavItems;

  const handleSelect = (slug: string) => {
    setIsOpen(false);
    if (onSelectCategory) {
      onSelectCategory(slug);
    } else {
      router.push(slug === "all" ? "/" : `/?category=${slug}`);
    }
  };

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const activeItem = items.find((i) => i.slug === activeCategory) || items[0];

  return (
    <nav
      ref={dropdownRef}
      className="w-full bg-nav-strip border-t border-line/20 text-xs tracking-wider uppercase font-semibold text-nav-text transition-colors duration-200"
    >
      <div className="max-w-[1360px] mx-auto px-4 sm:px-6">
        {/* Mobile View: Category Toggler Button + Scrollable Quick List */}
        <div className="flex md:hidden items-center py-2 gap-2">
          {/* Mobile Category Toggler Button */}
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-all cursor-pointer shrink-0 border ${
              isOpen
                ? "bg-nav-active text-nav-active-text border-nav-active font-bold shadow-xs"
                : "bg-white/10 hover:bg-white/20 text-nav-text border-white/20"
            }`}
            aria-expanded={isOpen}
            aria-label="Toggle categories"
          >
            <span className="material-symbols-outlined text-[18px]">
              {isOpen ? "close" : "grid_view"}
            </span>
            <span className="font-bold text-[11px] tracking-wide">Categories</span>
            <span
              className={`material-symbols-outlined text-[16px] transition-transform duration-200 ${
                isOpen ? "rotate-180" : ""
              }`}
            >
              expand_more
            </span>
          </button>

          {/* Quick swipeable category pills on mobile */}
          <div className="flex items-center space-x-1.5 overflow-x-auto whitespace-nowrap flex-1 py-0.5" style={{ scrollbarWidth: "none" }}>
            {items.map((item) => {
              const isActive = activeCategory === item.slug;
              return (
                <button
                  key={item.slug}
                  type="button"
                  onClick={() => handleSelect(item.slug)}
                  className={`px-2.5 py-1 rounded transition-all shrink-0 cursor-pointer text-[11px] ${
                    isActive
                      ? "bg-nav-active text-nav-active-text font-bold shadow-xs"
                      : "hover:text-surface hover:bg-white/10"
                  }`}
                >
                  {item.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Desktop View: Full Category Navigation Strip */}
        <div className="hidden md:flex items-center space-x-1 sm:space-x-2 py-2 whitespace-nowrap overflow-x-auto">
          {items.map((item) => {
            const isActive = activeCategory === item.slug;
            return (
              <button
                key={item.slug}
                type="button"
                onClick={() => handleSelect(item.slug)}
                className={`px-3 py-1 rounded transition-all cursor-pointer ${
                  isActive
                    ? "bg-nav-active text-nav-active-text font-bold shadow-sm"
                    : "hover:text-surface hover:bg-white/10"
                }`}
              >
                {item.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Mobile Collapsible Category Dropdown */}
      {isOpen && (
        <div className="md:hidden border-t border-line/20 bg-nav-strip/98 backdrop-blur-md px-4 py-3 shadow-xl">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-line/20 text-[11px] text-nav-text/70 uppercase font-bold tracking-wider">
            <span>Select Category</span>
            <span className="text-[10px] lowercase font-normal opacity-80">
              Active: <strong className="uppercase font-bold text-nav-text">{activeItem.name}</strong>
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1.5 max-h-72 overflow-y-auto pr-1">
            {items.map((item) => {
              const isActive = activeCategory === item.slug;
              return (
                <button
                  key={item.slug}
                  type="button"
                  onClick={() => handleSelect(item.slug)}
                  className={`flex items-center justify-between px-3 py-2 rounded text-xs font-semibold tracking-wide transition-all text-left cursor-pointer ${
                    isActive
                      ? "bg-nav-active text-nav-active-text font-bold shadow-xs"
                      : "bg-white/5 hover:bg-white/15 text-nav-text"
                  }`}
                >
                  <span className="truncate">{item.name}</span>
                  {isActive && (
                    <span className="material-symbols-outlined text-[16px] shrink-0 ml-1">
                      check
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </nav>
  );
}
