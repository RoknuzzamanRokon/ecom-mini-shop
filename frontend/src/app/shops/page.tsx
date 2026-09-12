"use client";

import React, { useEffect, useState, useTransition } from "react";
import Image from "next/image";
import Link from "next/link";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import Pagination from "@/components/home/Pagination";
import { Category, Shop } from "@/lib/types";
import { getCategories, getShops, formatImageUrl } from "@/lib/api";

const PAGE_SIZE = 12;

export default function ShopsDirectoryPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [, startTransition] = useTransition();

  useEffect(() => {
    getCategories().then(setCategories);
  }, []);

  useEffect(() => {
    let isCancelled = false;
    async function loadShops() {
      setLoading(true);
      const res = await getShops({
        search: searchQuery || undefined,
        page: currentPage,
        page_size: PAGE_SIZE,
      });
      if (!isCancelled) {
        setShops(res.results);
        setTotalCount(res.count);
        setTotalPages(Math.max(Math.ceil(res.count / PAGE_SIZE), 1));
        setLoading(false);
      }
    }
    loadShops();
    return () => {
      isCancelled = true;
    };
  }, [searchQuery, currentPage]);

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
        <Navbar categories={categories} />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full flex flex-col gap-6">
        {/* Breadcrumbs */}
        <nav className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/" className="hover:text-primary transition-colors">
            Home
          </Link>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-ink font-medium">Shops</span>
        </nav>

        {/* Page Header */}
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-[32px] text-accent">storefront</span>
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink tracking-tight">
              All Shops
            </h1>
            <p className="text-xs sm:text-sm text-ink-body mt-0.5">
              {loading ? "Loading shops..." : `${totalCount} shop${totalCount === 1 ? "" : "s"} on the platform`}
            </p>
          </div>
        </div>

        {/* Shop Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
          </div>
        ) : shops.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <span className="material-symbols-outlined text-[64px] text-ink-muted/50 mb-2">
              storefront
            </span>
            <h2 className="text-xl font-bold text-ink">No Shops Found</h2>
            <p className="text-sm text-ink-body mt-1">
              {searchQuery
                ? `No shops match "${searchQuery}".`
                : "There are no active shops on the platform yet."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {shops.map((shop) => (
              <Link
                key={shop.id}
                href={`/shop/${shop.slug}`}
                className="group flex flex-col rounded-2xl border border-line bg-surface shadow-sm hover:shadow-md transition-shadow overflow-hidden"
              >
                {/* Cover */}
                <div className="h-28 w-full relative bg-linear-to-r from-primary/20 via-surface-alt to-primary/10 overflow-hidden">
                  {shop.cover_image ? (
                    <Image
                      src={formatImageUrl(shop.cover_image)}
                      alt={`${shop.name} Cover`}
                      fill
                      className="object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-end pr-6 opacity-10 pointer-events-none">
                      <span className="material-symbols-outlined text-[90px] text-primary select-none">
                        storefront
                      </span>
                    </div>
                  )}
                </div>

                {/* Identity */}
                <div className="px-4 pb-4 pt-0 -mt-8 flex flex-col gap-2">
                  <div className="w-16 h-16 rounded-xl border-4 border-surface bg-surface-alt shadow-md overflow-hidden flex items-center justify-center shrink-0">
                    {shop.logo ? (
                      <Image
                        src={formatImageUrl(shop.logo)}
                        alt={`${shop.name} Logo`}
                        width={64}
                        height={64}
                        className="object-cover w-full h-full"
                      />
                    ) : (
                      <span className="material-symbols-outlined text-[28px] text-primary">
                        storefront
                      </span>
                    )}
                  </div>

                  <h3 className="text-sm font-bold text-ink truncate group-hover:text-primary transition-colors">
                    {shop.name}
                  </h3>

                  {shop.description && (
                    <p className="text-xs text-ink-body line-clamp-2 leading-relaxed">
                      {shop.description}
                    </p>
                  )}

                  {shop.address && (
                    <p className="flex items-center gap-1 text-[11px] text-ink-muted truncate">
                      <span className="material-symbols-outlined text-[14px] shrink-0">
                        location_on
                      </span>
                      {shop.address}
                    </p>
                  )}

                  <span className="mt-1 inline-flex items-center gap-1 text-xs font-bold text-primary">
                    Visit Shop
                    <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}

        {!loading && totalPages > 1 && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={(p) => setCurrentPage(p)}
          />
        )}
      </main>

      <Footer />
    </div>
  );
}
