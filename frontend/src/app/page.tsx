"use client";

import React, { useEffect, useState, useTransition } from "react";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import CategorySidebar from "@/components/home/CategorySidebar";
import HotDealWidget from "@/components/home/HotDealWidget";
import HeroBanner from "@/components/home/HeroBanner";
import ProductGrid from "@/components/home/ProductGrid";
import Pagination from "@/components/home/Pagination";
import { Category, Product } from "@/lib/types";
import { getCategories, getHotDeal, getProducts } from "@/lib/api";

export default function HomePage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [hotDeal, setHotDeal] = useState<Product | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
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

  const handleCategoryChange = (slug: string) => {
    startTransition(() => {
      setSelectedCategory(slug);
      setCurrentPage(1);
    });
  };

  const handleSearch = (q: string) => {
    startTransition(() => {
      setSearchQuery(q);
      setCurrentPage(1);
    });
  };

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      {/* Sticky Top Navigation Bar (Header + Category Strip) */}
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header onSearch={handleSearch} searchQuery={searchQuery} />
        <Navbar
          categories={categories}
          activeCategory={selectedCategory}
          onSelectCategory={handleCategoryChange}
        />
      </div>

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
                onPageChange={(p) => setCurrentPage(p)}
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
