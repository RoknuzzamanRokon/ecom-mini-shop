"use client";

import React, { useCallback, useEffect, useState, useTransition } from "react";
import Image from "next/image";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import ProductCard from "@/components/home/ProductCard";
import Pagination from "@/components/home/Pagination";
import StarRating from "@/components/reviews/StarRating";
import ShopReviews, { SHOP_REVIEWS_ANCHOR } from "@/components/reviews/ShopReviews";
import { Category, Product, Shop } from "@/lib/types";
import { getCategories, getProducts, getShopDetail, formatImageUrl } from "@/lib/api";

export default function ShopStorefrontPage() {
  const params = useParams();
  const slug = params?.slug as string;

  const [shop, setShop] = useState<Shop | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loadingShop, setLoadingShop] = useState<boolean>(true);
  const [loadingProducts, setLoadingProducts] = useState<boolean>(true);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [ordering, setOrdering] = useState<string>("-created_at");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const [, startTransition] = useTransition();

  // Load shop details and global categories
  useEffect(() => {
    async function loadShopAndCategories() {
      if (!slug) return;
      setLoadingShop(true);
      const [shopData, cats] = await Promise.all([
        getShopDetail(slug),
        getCategories(),
      ]);
      setShop(shopData);
      setCategories(cats);
      setLoadingShop(false);
    }
    loadShopAndCategories();
  }, [slug]);

  // Load shop products whenever filters change
  useEffect(() => {
    let isCancelled = false;
    async function loadShopProducts() {
      if (!slug) return;
      setLoadingProducts(true);
      const res = await getProducts({
        shop: slug,
        category: selectedCategory,
        q: searchQuery,
        ordering: ordering,
        page: currentPage,
        page_size: 12,
      });

      if (!isCancelled) {
        setProducts(res.results);
        setTotalCount(res.count);
        setTotalPages(Math.max(Math.ceil(res.count / 12), 1));
        setLoadingProducts(false);
      }
    }
    loadShopProducts();
    return () => {
      isCancelled = true;
    };
  }, [slug, selectedCategory, searchQuery, ordering, currentPage]);

  // After a review is added, edited or deleted, refetch the shop so the header
  // rating and the summary bars catch up. A failed refetch keeps the shop on
  // screen rather than falling through to the not-found state.
  const refreshShop = useCallback(async () => {
    if (!slug) return;
    const shopData = await getShopDetail(slug);
    if (shopData) setShop(shopData);
  }, [slug]);

  const handleCategoryChange = (catSlug: string) => {
    startTransition(() => {
      setSelectedCategory(catSlug);
      setCurrentPage(1);
    });
  };

  const handleSearch = (q: string) => {
    startTransition(() => {
      setSearchQuery(q);
      setCurrentPage(1);
    });
  };

  const handleOrderingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    startTransition(() => {
      setOrdering(e.target.value);
      setCurrentPage(1);
    });
  };

  if (loadingShop) {
    return (
      <div className="min-h-screen flex flex-col bg-page">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
        </div>
        <Footer />
      </div>
    );
  }

  // No published shop under this slug is a 404, not a failure. The segment's
  // not-found boundary owns that state; `error.tsx` stays reserved for a crash
  // while rendering a shop that does exist.
  if (!shop) {
    notFound();
  }

  const memberSinceYear = shop.created_at
    ? new Date(shop.created_at).getFullYear()
    : new Date().getFullYear();
  const shopRating = shop.average_rating ?? 0;
  const shopReviewCount = shop.review_count ?? 0;

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      {/* Sticky Navigation Strip */}
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header onSearch={handleSearch} searchQuery={searchQuery} />
        <Navbar
          categories={categories}
          activeCategory={selectedCategory}
          onSelectCategory={handleCategoryChange}
        />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full flex flex-col gap-6">
        {/* Breadcrumbs */}
        <nav className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/" className="hover:text-primary transition-colors">
            Home
          </Link>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-ink-muted">Shops</span>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-ink font-medium truncate">{shop.name}</span>
        </nav>

        {/* Shop Storefront Hero Header */}
        <section className="relative rounded-2xl overflow-hidden border border-line bg-surface shadow-sm">
          {/* Cover Banner */}
          <div className="h-44 sm:h-56 w-full relative bg-linear-to-r from-primary/20 via-surface-alt to-primary/10 overflow-hidden">
            {shop.cover_image ? (
              <Image
                src={formatImageUrl(shop.cover_image)}
                alt={`${shop.name} Cover`}
                fill
                className="object-cover"
                priority
              />
            ) : (
              <div className="w-full h-full flex items-center justify-end pr-12 opacity-10 pointer-events-none">
                <span className="material-symbols-outlined text-[180px] text-primary select-none">
                  storefront
                </span>
              </div>
            )}
            <div className="absolute inset-0 bg-linear-to-t from-surface via-surface/30 to-transparent" />
          </div>

          {/* Shop Profile Bar */}
          <div className="px-6 pb-6 pt-0 relative -mt-16 sm:-mt-20 flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
              {/* Logo / Avatar */}
              <div className="relative w-24 h-24 sm:w-28 sm:h-28 rounded-2xl border-4 border-surface bg-surface-alt shadow-md overflow-hidden shrink-0 flex items-center justify-center">
                {shop.logo ? (
                  <Image
                    src={formatImageUrl(shop.logo)}
                    alt={`${shop.name} Logo`}
                    fill
                    className="object-cover"
                  />
                ) : (
                  <span className="material-symbols-outlined text-[48px] text-primary">
                    storefront
                  </span>
                )}
              </div>

              {/* Identity & Status */}
              <div className="flex flex-col">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h1 className="text-2xl sm:text-3xl font-black text-ink tracking-tight">
                    {shop.name}
                  </h1>
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-success/10 text-success border border-success/30 uppercase">
                    <span className="w-1.5 h-1.5 rounded-full bg-success"></span>
                    Verified Seller
                  </span>
                </div>

                {shop.description && (
                  <p className="text-xs sm:text-sm text-ink-body mt-1 max-w-2xl leading-relaxed">
                    {shop.description}
                  </p>
                )}

                {/* Shop Metadata Pills */}
                <div className="flex items-center gap-4 flex-wrap mt-2.5 text-xs text-ink-muted font-medium">
                  <a
                    href={`#${SHOP_REVIEWS_ANCHOR}`}
                    className="flex items-center gap-1.5 hover:text-primary transition-colors"
                    title="See customer reviews"
                  >
                    <StarRating rating={shopRating} size={15} />
                    {shopReviewCount > 0 ? (
                      <span>
                        <strong className="text-ink">{shopRating.toFixed(1)}</strong> ·{" "}
                        {shopReviewCount} review{shopReviewCount === 1 ? "" : "s"}
                      </span>
                    ) : (
                      <span>No reviews yet</span>
                    )}
                  </a>

                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[16px] text-primary">
                      inventory_2
                    </span>
                    <strong className="text-ink">{totalCount}</strong> Products
                  </span>

                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[16px] text-primary">
                      verified
                    </span>
                    Member since {memberSinceYear}
                  </span>

                  {shop.address && (
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[16px] text-primary">
                        location_on
                      </span>
                      {shop.address}
                    </span>
                  )}

                  {shop.phone && (
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[16px] text-primary">
                        call
                      </span>
                      {shop.phone}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Trust Badges */}
            <div className="hidden lg:flex items-center gap-3 shrink-0 bg-surface-alt/60 p-3 rounded-xl border border-line">
              <div className="flex flex-col items-center text-center px-2">
                <span className="text-xs font-bold text-ink">100% Authentic</span>
                <span className="text-[10px] text-ink-muted">Direct from Seller</span>
              </div>
              <div className="w-px h-8 bg-line" />
              <div className="flex flex-col items-center text-center px-2">
                <span className="text-xs font-bold text-ink">Express Delivery</span>
                <span className="text-[10px] text-ink-muted">Nationwide via ৳</span>
              </div>
            </div>
          </div>
        </section>

        {/* Shop Catalog Controls Bar */}
        <div className="bg-surface rounded-xl border border-line p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Search inside shop */}
          <div className="relative flex-1 max-w-md">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-ink-muted pointer-events-none">
              search
            </span>
            <input
              type="text"
              placeholder={`Search products in ${shop.name}...`}
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              className="w-full bg-surface-alt border border-line rounded-lg pl-9 pr-3 py-2 text-xs text-ink placeholder:text-ink-muted focus:outline-hidden focus:border-primary focus:ring-1 focus:ring-primary transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => handleSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink cursor-pointer"
                title="Clear search"
              >
                <span className="material-symbols-outlined text-[16px]">close</span>
              </button>
            )}
          </div>

          {/* Right Controls: Categories filter, Sorting, View Toggle */}
          <div className="flex items-center gap-3 flex-wrap justify-between md:justify-end">
            {/* Category Dropdown */}
            <select
              value={selectedCategory}
              onChange={(e) => handleCategoryChange(e.target.value)}
              className="bg-surface-alt border border-line rounded-lg px-3 py-2 text-xs font-medium text-ink focus:outline-hidden focus:border-primary cursor-pointer"
            >
              <option value="all">All Categories</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.slug}>
                  {cat.name}
                </option>
              ))}
            </select>

            {/* Sorting Dropdown */}
            <select
              value={ordering}
              onChange={handleOrderingChange}
              className="bg-surface-alt border border-line rounded-lg px-3 py-2 text-xs font-medium text-ink focus:outline-hidden focus:border-primary cursor-pointer"
            >
              <option value="-created_at">Sort: Newest First</option>
              <option value="-rating">Top Rated</option>
              <option value="price">Price: Low to High</option>
              <option value="-price">Price: High to Low</option>
              <option value="name">Name: A to Z</option>
            </select>

            {/* View Mode Toggle */}
            <div className="flex items-center border border-line rounded-lg overflow-hidden bg-surface-alt p-0.5">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-1.5 rounded transition-colors cursor-pointer ${
                  viewMode === "grid"
                    ? "bg-surface text-primary shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="Grid View"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px] block">grid_view</span>
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`p-1.5 rounded transition-colors cursor-pointer ${
                  viewMode === "list"
                    ? "bg-surface text-primary shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="List View"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px] block">view_list</span>
              </button>
            </div>
          </div>
        </div>

        {/* Products Listing */}
        <section className="flex flex-col gap-6">
          {loadingProducts ? (
            <div className="py-20 flex flex-col items-center justify-center text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary mb-3"></div>
              <p className="text-xs text-ink-muted">Loading products from {shop.name}...</p>
            </div>
          ) : products.length === 0 ? (
            <div className="bg-surface rounded-xl border border-line p-12 text-center flex flex-col items-center justify-center">
              <span className="material-symbols-outlined text-[56px] text-ink-muted/40 mb-2">
                inventory_2
              </span>
              <h3 className="text-base font-bold text-ink">No Products Found</h3>
              <p className="text-xs text-ink-body mt-1 max-w-sm">
                No products from {shop.name} matched your current filter or search criteria.
              </p>
              {(selectedCategory !== "all" || searchQuery) && (
                <button
                  onClick={() => {
                    setSelectedCategory("all");
                    setSearchQuery("");
                    setCurrentPage(1);
                  }}
                  className="mt-4 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  Clear All Filters
                </button>
              )}
            </div>
          ) : (
            <>
              {viewMode === "grid" ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 gap-4">
                  {products.map((product) => (
                    <ProductCard key={product.id} product={product} viewMode="grid" />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {products.map((product) => (
                    <ProductCard key={product.id} product={product} viewMode="list" />
                  ))}
                </div>
              )}

              {/* Pagination */}
              {totalPages > 1 && (
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={(page) => setCurrentPage(page)}
                />
              )}
            </>
          )}
        </section>

        {/* Shop reviews: separate from the reviews of the shop's products */}
        <ShopReviews
          shopId={shop.id}
          shopSlug={shop.slug}
          averageRating={shop.average_rating}
          reviewCount={shop.review_count}
          ratingBreakdown={shop.rating_breakdown}
          onReviewsChanged={refreshShop}
        />
      </main>

      <Footer />
    </div>
  );
}
