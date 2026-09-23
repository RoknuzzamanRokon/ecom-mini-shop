"use client";

import React, { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { notFound, useParams, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import ProductCard from "@/components/home/ProductCard";
import ProductImageZoom from "@/components/product/ProductImageZoom";
import FavoriteButton from "@/components/product/FavoriteButton";
import ProductReviews from "@/components/product/ProductReviews";
import StarRating from "@/components/reviews/StarRating";
import { Product } from "@/lib/types";
import { getProductDetail, formatImageUrl } from "@/lib/api";
import { useCart } from "@/context/CartContext";

export default function ProductDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;

  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string>("/placeholder.svg");
  const [quantity, setQuantity] = useState(1);
  const { addToCart } = useCart();

  const handleBuyNow = () => {
    if (!product || !product.in_stock) return;
    addToCart(product, quantity);
    router.push("/checkout");
  };

  const loadProduct = useCallback(
    async (showSpinner: boolean) => {
      if (!slug) return;
      if (showSpinner) setLoading(true);
      const data = await getProductDetail(slug);
      if (data) {
        setProduct(data);
        if (showSpinner) {
          const mainImg = formatImageUrl(data.image_url || (data.image ? data.image : ""));
          setSelectedImage(mainImg);
        }
      }
      if (showSpinner) setLoading(false);
    },
    [slug]
  );

  useEffect(() => {
    loadProduct(true);
  }, [loadProduct]);

  if (loading) {
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

  // A slug with no product behind it is a 404, not a failure. Handing it to the
  // segment's not-found boundary keeps that distinct from `error.tsx`, which is
  // reserved for an actual crash while rendering an existing product.
  if (!product) {
    notFound();
  }

  const galleryImages =
    product.all_image_urls && product.all_image_urls.length > 0
      ? product.all_image_urls
      : selectedImage
      ? [selectedImage]
      : [];

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-2 text-xs text-ink-muted mb-6">
          <Link href="/" className="hover:text-primary transition-colors">
            Home
          </Link>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          {product.category && (
            <>
              <Link href={`/?category=${product.category.slug}`} className="hover:text-primary transition-colors">
                {product.category.name}
              </Link>
              <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            </>
          )}
          <span className="text-ink font-medium truncate">{product.name}</span>
        </nav>

        {/* Product Details Section */}
        <div className="bg-surface rounded-xl border border-line p-6 lg:p-8 shadow-sm grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left: Gallery (Compact, balanced 5 cols) */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <ProductImageZoom
              src={selectedImage}
              alt={product.name}
              badge={product.badge}
              fallbackSrc="/placeholder.svg"
            />

            {/* Thumbnail selector */}
            {galleryImages.length > 1 && (
              <div className="flex gap-2.5 overflow-x-auto pb-1">
                {galleryImages.map((img, i) => {
                  const formattedThumb = formatImageUrl(img);
                  return (
                    <button
                      key={i}
                      onClick={() => setSelectedImage(formattedThumb)}
                      className={`relative w-16 h-16 rounded-md overflow-hidden border-2 shrink-0 transition-all cursor-pointer ${
                        selectedImage === formattedThumb
                          ? "border-primary shadow-xs"
                          : "border-line hover:border-ink-muted"
                      }`}
                    >
                      <Image src={formattedThumb} alt={`Thumb ${i}`} fill className="object-cover" />
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Info & Actions (Spacious 7 cols) */}
          <div className="lg:col-span-7 flex flex-col">
            <span className="text-xs uppercase font-bold tracking-widest text-primary">
              {product.category?.name || "Catalog"}
            </span>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink mt-1.5 tracking-tight">
              {product.name}
            </h1>

            {/* Rating */}
            <div className="flex items-center gap-2 mt-2.5">
              <StarRating rating={product.average_rating ?? 0} size={16} />
              {(product.review_count ?? 0) > 0 && (
                <span className="text-xs font-bold text-ink">
                  {(product.average_rating ?? 0).toFixed(1)}
                </span>
              )}
              <span className="text-xs font-semibold text-ink-muted">
                {product.review_count
                  ? `${product.review_count} customer review${product.review_count === 1 ? "" : "s"}`
                  : "No reviews yet"}
              </span>
            </div>

            {/* Price Box */}
            <div className="mt-4 p-4 rounded-lg bg-surface-alt/60 border border-line flex items-baseline gap-3">
              <span className="text-2xl sm:text-3xl font-extrabold text-primary">
                ৳{product.price}
              </span>
              {product.old_price && (
                <span className="text-base text-price-old line-through">
                  ৳{product.old_price}
                </span>
              )}
              {product.savings_amount && (
                <span className="ml-auto bg-badge-hot/10 text-badge-hot border border-badge-hot/30 text-xs font-bold px-2.5 py-1 rounded">
                  Save ৳{product.savings_amount}
                </span>
              )}
            </div>

            {/* Stock status */}
            <div className="mt-4 flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  product.in_stock ? "bg-success" : "bg-danger"
                }`}
              />
              <span className="text-xs font-semibold text-ink">
                {product.in_stock ? `In Stock (${product.stock} available)` : "Out of Stock"}
              </span>
            </div>

            {/* Shop Information & Visit Shop */}
            {product.shop && (
              <div className="mt-4 p-3.5 rounded-lg bg-surface-alt/40 border border-line flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                    <span className="material-symbols-outlined text-[20px]">storefront</span>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[11px] text-ink-muted">Sold by:</span>
                      <span className="font-bold text-xs text-ink truncate">{product.shop.name}</span>
                      <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-success/10 text-success border border-success/30 uppercase">
                        Active
                      </span>
                    </div>
                    <p className="text-[11px] text-ink-muted mt-0.5">Verified seller store on MiniShop</p>
                  </div>
                </div>
                <Link
                  href={`/shop/${product.shop.slug}`}
                  className="shrink-0 text-xs font-semibold text-primary hover:text-primary-hover flex items-center gap-1 transition-colors border border-primary/20 hover:border-primary/50 bg-surface px-3 py-1.5 rounded-md shadow-2xs hover:shadow-xs"
                >
                  <span>Visit Shop</span>
                  <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                </Link>
              </div>
            )}

            {/* Description */}
            <p className="text-sm text-ink-body mt-4 leading-relaxed">
              {product.description}
            </p>

            {/* Quantity and Actions (Add to Cart & Buy Now) */}
            <div className="mt-6 pt-6 border-t border-line flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="flex items-center border border-line rounded-lg bg-surface overflow-hidden w-fit">
                <button
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  className="px-3.5 py-2.5 text-sm text-ink hover:bg-surface-sunken transition-colors cursor-pointer"
                  type="button"
                >
                  -
                </button>
                <span className="px-4 py-2.5 text-sm font-bold text-ink min-w-[3rem] text-center">
                  {quantity}
                </span>
                <button
                  onClick={() => setQuantity(quantity + 1)}
                  className="px-3.5 py-2.5 text-sm text-ink hover:bg-surface-sunken transition-colors cursor-pointer"
                  type="button"
                >
                  +
                </button>
              </div>

              <button
                onClick={() => addToCart(product, quantity)}
                disabled={!product.in_stock}
                className="flex-1 bg-surface-alt hover:bg-surface-sunken border border-line disabled:opacity-50 text-ink font-bold text-xs uppercase tracking-wider py-3 px-4 rounded-lg shadow-2xs transition-all flex items-center justify-center gap-2 cursor-pointer active:scale-98"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">add_shopping_cart</span>
                <span>Add to Cart</span>
              </button>

              <button
                onClick={handleBuyNow}
                disabled={!product.in_stock}
                className="flex-1 bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider py-3 px-4 rounded-lg shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer active:scale-98"
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">bolt</span>
                <span>Buy Now</span>
              </button>

              <FavoriteButton productId={product.id} size="md" />
            </div>

            {/* Perks breakdown */}
            <div className="mt-8 grid grid-cols-2 gap-3 pt-6 border-t border-line text-xs text-ink-body">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[18px]">
                  local_shipping
                </span>
                <span>Free shipping over ৳99</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[18px]">
                  verified_user
                </span>
                <span>30-day money back guarantee</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[18px]">
                  workspace_premium
                </span>
                <span>100% Genuine product</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[18px]">
                  support_agent
                </span>
                <span>24/7 dedicated support</span>
              </div>
            </div>
          </div>
        </div>

        <ProductReviews productId={product.id} onReviewsChanged={() => loadProduct(false)} />

        {/* Related Products */}
        {product.related_products && product.related_products.length > 0 && (
          <div className="mt-12">
            <h3 className="font-bold text-base uppercase tracking-wider text-ink mb-4">
              Related Products
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {product.related_products.map((rel) => (
                <ProductCard key={rel.id} product={rel} />
              ))}
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
