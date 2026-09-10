"use client";

import React, { useState, useEffect, useMemo } from "react";
import Image from "next/image";
import { Category } from "@/lib/types";
import { formatImageUrl } from "@/lib/api";

interface HeroBannerProps {
  activeCategory?: string;
  categories?: Category[];
  onSelectCategory?: (slug: string) => void;
}

interface CategoryMeta {
  subtitle: string;
  titlePrimary: string;
  titleAccent: string;
  description: string;
  fallbackImage: string;
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  clothing: {
    subtitle: "SPRING 2025",
    titlePrimary: "WOMEN & MEN",
    titleAccent: "FASHION",
    description:
      "Carefully curated essentials designed for everyday comfort, timeless modern silhouettes, and architectural elegance.",
    fallbackImage:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuCSVwxG52Hz7vhpEWeXPi5UJm20e7TlgZtWZbHszLI4cifI7F5uPYFbxEy59NIlYWIUigqpNJ2egy32cewdQGxDTxh8kV6bZ4Nf3w3s4jW6RW8lR0YCkvt9InRkL9IWpB-tIKgwd5-gZ27tVGExSWYVzPjmxSQkjJsfrPKBicGIs9IV5ytAnf5usn6PU6lCg0h8tocx1ADCxwNN9AUQJhhhCJ3zCib2ZZadlDXWecBkEWqBrt2ESFdvQQ",
  },
  electronics: {
    subtitle: "TECH ESSENTIALS",
    titlePrimary: "INNOVATIVE",
    titleAccent: "ELECTRONICS",
    description:
      "Cutting-edge audio, custom mechanical keyboards, smart wearable fitness trackers, and modern everyday workspace gear.",
    fallbackImage: "/placeholder.svg",
  },
  shoes: {
    subtitle: "MODERN MOTION",
    titlePrimary: "FOOTWEAR &",
    titleAccent: "SHOES",
    description:
      "Everyday cushioned canvas sneakers, lightweight trail runners, and versatile footwear built for modern motion.",
    fallbackImage: "/placeholder.svg",
  },
  watches: {
    subtitle: "PRECISION CRAFT",
    titlePrimary: "CLASSIC & SPORT",
    titleAccent: "WATCHES",
    description:
      "Precision timepieces featuring genuine leather straps, scratch-resistant sapphire crystals, and chronograph detailing.",
    fallbackImage: "/placeholder.svg",
  },
  jewellery: {
    subtitle: "ARTISAN FINISH",
    titlePrimary: "HANDCRAFTED",
    titleAccent: "JEWELLERY",
    description:
      "Delicate sterling silver necklaces, hand-finished pendants, and natural stone beaded bracelet sets for all occasions.",
    fallbackImage: "/placeholder.svg",
  },
  "health-and-beauty": {
    subtitle: "ORGANIC RADIANCE",
    titlePrimary: "HEALTH &",
    titleAccent: "BEAUTY",
    description:
      "Clean botanical face serums, natural bamboo grooming essentials, and restorative wellness care for everyday vitality.",
    fallbackImage: "/placeholder.svg",
  },
  "kids-and-babies": {
    subtitle: "LITTLE WONDERS",
    titlePrimary: "KIDS &",
    titleAccent: "BABIES",
    description:
      "Ultra-soft gentle cotton essentials, playful educational puzzle sets, and cuddly plush toys made for curious minds.",
    fallbackImage: "/placeholder.svg",
  },
  sports: {
    subtitle: "ACTIVE LIVING",
    titlePrimary: "SPORTS &",
    titleAccent: "FITNESS",
    description:
      "High-performance workout equipment, premium studio yoga mats, and durable athletic gear built for an active lifestyle.",
    fallbackImage: "/placeholder.svg",
  },
  "home-and-garden": {
    subtitle: "LIVING SPACES",
    titlePrimary: "HOME &",
    titleAccent: "GARDEN",
    description:
      "Elevate your indoor spaces with artisan ceramic mugs, modern planters, cozy desk lamps, and architectural decor.",
    fallbackImage: "/placeholder.svg",
  },
};

export default function HeroBanner({
  activeCategory = "all",
  categories = [],
  onSelectCategory,
}: HeroBannerProps) {
  const isSingleCategory = Boolean(activeCategory && activeCategory !== "all");

  // Construct category slides for home/all mode
  const slides = useMemo(() => {
    if (categories && categories.length > 0) {
      return categories
        .filter((cat) => cat.is_active !== false)
        .map((cat) => {
          const meta = CATEGORY_META[cat.slug] || {
            subtitle: "EXPLORE COLLECTION",
            titlePrimary: cat.name.toUpperCase(),
            titleAccent: "COLLECTION",
            description:
              cat.description || "Discover high-quality essentials curated for modern living.",
            fallbackImage: "/placeholder.svg",
          };
          const imageSrc = cat.image_url ? formatImageUrl(cat.image_url) : meta.fallbackImage;
          return {
            slug: cat.slug,
            name: cat.name,
            subtitle: meta.subtitle,
            titlePrimary: meta.titlePrimary,
            titleAccent: meta.titleAccent,
            description: cat.description || meta.description,
            image: imageSrc,
            count: cat.products_count,
          };
        });
    }

    // Default fallback slides before categories load
    return Object.entries(CATEGORY_META).map(([slug, meta]) => ({
      slug,
      name: meta.titleAccent || slug,
      subtitle: meta.subtitle,
      titlePrimary: meta.titlePrimary,
      titleAccent: meta.titleAccent,
      description: meta.description,
      image: meta.fallbackImage,
      count: undefined,
    }));
  }, [categories]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);

  // Auto-play animation timer for the slider when on home/all categories
  useEffect(() => {
    if (isSingleCategory || slides.length <= 1 || isPaused) return;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % slides.length);
    }, 4500);

    return () => clearInterval(interval);
  }, [isSingleCategory, slides.length, isPaused]);

  // Reset slide index if categories change
  useEffect(() => {
    if (currentIndex >= slides.length) {
      setCurrentIndex(0);
    }
  }, [slides.length, currentIndex]);

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev - 1 + slides.length) % slides.length);
  };

  const handleNext = () => {
    setCurrentIndex((prev) => (prev + 1) % slides.length);
  };

  // Dedicated single category view (e.g. Shoes, Clothing, etc.)
  if (isSingleCategory) {
    const activeCat = categories.find((c) => c.slug === activeCategory);
    const meta = CATEGORY_META[activeCategory] || {
      subtitle: "CATEGORY SHOWCASE",
      titlePrimary: activeCat ? activeCat.name.toUpperCase() : activeCategory.toUpperCase(),
      titleAccent: "COLLECTION",
      description:
        activeCat?.description || "Explore our curated collection of high-quality products.",
      fallbackImage: "/placeholder.svg",
    };
    const categoryImage = activeCat?.image_url
      ? formatImageUrl(activeCat.image_url)
      : meta.fallbackImage;

    return (
      <div className="bg-surface rounded-lg border border-line overflow-hidden shadow-sm transition-colors duration-200">
        <div className="relative bg-gradient-to-r from-surface-alt via-surface to-surface-alt/40 min-h-[260px] sm:min-h-[300px] flex items-center">
          {/* Left Text Info */}
          <div className="w-full sm:w-3/5 p-6 sm:p-10 z-10">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="inline-flex items-center gap-1 text-[11px] uppercase font-bold tracking-widest text-accent bg-accent/10 border border-accent/20 px-2.5 py-0.5 rounded">
                <span className="material-symbols-outlined text-[14px]">category</span>
                <span>{meta.subtitle}</span>
              </span>
              {activeCat?.products_count !== undefined && (
                <span className="text-xs font-semibold text-ink-muted">
                  • {activeCat.products_count} Items Available
                </span>
              )}
            </div>

            <h2 className="text-2xl sm:text-4xl font-extrabold text-ink tracking-tight mt-1 mb-2">
              {meta.titlePrimary} <span className="text-accent">{meta.titleAccent}</span>
            </h2>

            <p className="text-xs sm:text-sm text-ink-body max-w-md line-clamp-3 mb-6 leading-relaxed">
              {activeCat?.description || meta.description}
            </p>

            <div className="flex flex-wrap items-center gap-3">
              <a
                href="#products-section"
                className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-5 py-2.5 rounded shadow-sm transition-all hover:shadow cursor-pointer"
              >
                <span>EXPLORE PRODUCTS</span>
                <span className="material-symbols-outlined text-[16px]">arrow_downward</span>
              </a>

              {onSelectCategory && (
                <button
                  type="button"
                  onClick={() => onSelectCategory("all")}
                  className="inline-flex items-center gap-1.5 bg-surface-alt hover:bg-surface-sunken text-ink font-semibold text-xs uppercase tracking-wider px-4 py-2.5 rounded border border-line transition-colors cursor-pointer"
                  title="View all categories"
                >
                  <span className="material-symbols-outlined text-[16px]">view_carousel</span>
                  <span>All Categories</span>
                </button>
              )}
            </div>
          </div>

          {/* Right Category Hero Photo */}
          <div className="hidden sm:block absolute right-0 bottom-0 top-0 w-2/5 overflow-hidden">
            <Image
              src={categoryImage}
              alt={activeCat?.name || activeCategory}
              fill
              sizes="40vw"
              unoptimized
              className="w-full h-full object-cover object-center mix-blend-multiply opacity-85 transition-opacity duration-300"
              priority
            />
          </div>
        </div>
      </div>
    );
  }

  // Multi-Category Animated Slider Mode (Home / All Products)
  const currentSlide = slides[currentIndex] || slides[0];

  return (
    <div
      className="group relative bg-surface rounded-lg border border-line overflow-hidden shadow-sm transition-colors duration-200"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <div className="relative bg-gradient-to-r from-surface-alt via-surface to-surface-alt/40 min-h-[260px] sm:min-h-[300px] flex items-center">
        {/* Left Slide Content */}
        <div className="w-full sm:w-3/5 p-6 sm:p-10 z-10">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs uppercase font-bold tracking-widest text-ink-muted">
              {currentSlide.subtitle}
            </span>
            <span className="text-[11px] font-mono text-ink-muted/80">
              ({currentIndex + 1}/{slides.length})
            </span>
          </div>

          <h2 className="text-2xl sm:text-4xl font-extrabold text-ink tracking-tight mt-1 mb-2 transition-all">
            {currentSlide.titlePrimary}{" "}
            <span className="text-accent">{currentSlide.titleAccent}</span>
          </h2>

          <p className="text-xs sm:text-sm text-ink-body max-w-md line-clamp-2 mb-5 leading-relaxed transition-all">
            {currentSlide.description}
          </p>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                if (onSelectCategory) {
                  onSelectCategory(currentSlide.slug);
                }
                const el = document.getElementById("products-section");
                if (el) el.scrollIntoView({ behavior: "smooth" });
              }}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded shadow-sm transition-all hover:shadow cursor-pointer"
            >
              <span>SHOP {currentSlide.name.toUpperCase()}</span>
              <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
            </button>
          </div>

          {/* Slider Indicator Dots */}
          <div className="flex items-center gap-1.5 mt-5">
            {slides.map((slide, idx) => (
              <button
                key={slide.slug || idx}
                type="button"
                onClick={() => setCurrentIndex(idx)}
                aria-label={`Go to slide ${idx + 1}: ${slide.name}`}
                className={`h-1.5 rounded-full transition-all duration-300 cursor-pointer ${
                  currentIndex === idx
                    ? "w-6 bg-primary"
                    : "w-2 bg-ink/20 hover:bg-ink/40"
                }`}
              />
            ))}
          </div>
        </div>

        {/* Right Slide Photo (with crossfade animation key) */}
        <div className="hidden sm:block absolute right-0 bottom-0 top-0 w-2/5 overflow-hidden">
          <Image
            key={currentSlide.slug}
            src={currentSlide.image}
            alt={currentSlide.name}
            fill
            sizes="40vw"
            unoptimized
            className="w-full h-full object-cover object-center mix-blend-multiply opacity-85 transition-opacity duration-500 animate-in fade-in"
            priority
          />
        </div>

        {/* Navigation Arrows (Visible on mobile and on hover on desktop) */}
        {slides.length > 1 && (
          <>
            <button
              type="button"
              onClick={handlePrev}
              aria-label="Previous slide"
              className="absolute left-2.5 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface/90 hover:bg-surface text-ink flex items-center justify-center shadow-md border border-line/50 transition-all opacity-80 sm:opacity-0 group-hover:opacity-100 cursor-pointer hover:scale-105 active:scale-95"
            >
              <span className="material-symbols-outlined text-[20px]">chevron_left</span>
            </button>

            <button
              type="button"
              onClick={handleNext}
              aria-label="Next slide"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full bg-surface/90 hover:bg-surface text-ink flex items-center justify-center shadow-md border border-line/50 transition-all opacity-80 sm:opacity-0 group-hover:opacity-100 cursor-pointer hover:scale-105 active:scale-95"
            >
              <span className="material-symbols-outlined text-[20px]">chevron_right</span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

