"use client";

import React, { Suspense, useEffect, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import StorefrontChrome from "@/components/layout/StorefrontChrome";
import Footer from "@/components/layout/Footer";
import CategorySidebar from "@/components/home/CategorySidebar";
import HotDealWidget from "@/components/home/HotDealWidget";
import HeroBanner from "@/components/home/HeroBanner";
import ProductGrid from "@/components/home/ProductGrid";
import Pagination from "@/components/home/Pagination";
import { Category, Product } from "@/lib/types";
import { getCategories, getHotDeal, getProducts } from "@/lib/api";

/**
 * The catalogue's category, search and page live in the URL (?category=,
 * ?q=, ?page=), so the Navbar, the Header search and breadcrumb links from
 * any page land on the right listing, and Back/Forward work (BUG-032/033).
 * useSearchParams needs a Suspense boundary for the static build.
 */
export default function HomePage() {
  return (
    <Suspense fallback={<HomeFallback />}>
      <HomeContent />
    </Suspense>
  );
}

function HomeFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
    </div>
  );
}

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedCategory = searchParams.get("category") || "all";
  const searchQuery = searchParams.get("q") || "";
  const currentPage = Math.max(1, Number.parseInt(searchParams.get("page") || "1", 10) || 1);

  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [hotDeal, setHotDeal] = useState<Product | null>(null);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [isPending, startTransition] = useTransition();

  // Load initial static/server data
  useEffect(() => {
    async function loadInitial() {
      const [cats, deal] = await Promise.all([getCategories(), getHotDeal()]);
      setCategories(cats);
      setHotDeal(deal);
    }
    loadInitial();
  }, []);

  // Fetch products whenever filters or page change
  useEffect(() => {
    let isCancelled = false;
    async function loadProducts() {
      setLoading(true);
      const res = await getProducts({
        category: selectedCategory,
        q: searchQuery,
        page: currentPage,
      });
      if (!isCancelled) {
        setProducts(res.results);
        setTotalPages(Math.max(Math.ceil(res.count / 12), 1));
        setLoading(false);
      }
    }
    loadProducts();
    return () => {
      isCancelled = true;
    };
  }, [selectedCategory, searchQuery, currentPage]);

  /** Writes the given keys into the URL (null removes one); any filter change returns to page 1. */
  const updateUrl = (changes: Record<string, string | null>, mode: "push" | "replace" = "push") => {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    const query = params.toString();
    const href = query ? `/?${query}` : "/";
    startTransition(() => {
      if (mode === "replace") router.replace(href, { scroll: false });
      else router.push(href, { scroll: false });
    });
  };

  const handleCategoryChange = (slug: string) => {
    updateUrl({ category: slug === "all" ? null : slug, page: null });
  };

  // The Header debounces typing, so this runs once per pause, not per key.
  const handleSearch = (q: string) => {
    const term = q.trim();
    if (term === searchQuery) return;
    updateUrl({ q: term || null, page: null }, "replace");
  };

  const handlePageChange = (page: number) => {
    updateUrl({ page: page > 1 ? String(page) : null });
  };

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      {/* Sticky Top Navigation Bar (Header + Category Strip) */}
      <StorefrontChrome
        onSearch={handleSearch}
        searchQuery={searchQuery}
        categories={categories}
        activeCategory={selectedCategory}
        onSelectCategory={handleCategoryChange}
      />

      {/* Main 2-Column Catalog Layout */}
      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* LEFT SIDEBAR: Categories & Hot Deals (hidden on mobile, 3 columns on lg screens) */}
          <aside className="hidden lg:flex lg:col-span-3 flex-col gap-6">
            <CategorySidebar
              categories={categories}
              activeCategory={selectedCategory}
              onSelectCategory={handleCategoryChange}
            />

            <HotDealWidget deal={hotDeal} />
          </aside>

          {/* RIGHT MAIN AREA: Banner, Product Grid & Pagination (full width on mobile, 9 columns on lg) */}
          <section className="w-full lg:col-span-9 flex flex-col gap-6">
            <HeroBanner
              activeCategory={selectedCategory}
              categories={categories}
              onSelectCategory={handleCategoryChange}
            />

            <ProductGrid
              products={products}
              selectedCategory={selectedCategory}
              onSelectCategory={handleCategoryChange}
              loading={loading || isPending}
            />

            {totalPages > 1 && (
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={handlePageChange}
              />
            )}
          </section>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}
