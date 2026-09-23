"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Product } from "@/lib/types";
import { useCart } from "@/context/CartContext";
import { formatImageUrl } from "@/lib/api";
import StarRating from "@/components/reviews/StarRating";

interface HotDealWidgetProps {
  deal: Product | null;
}

export default function HotDealWidget({ deal }: HotDealWidgetProps) {
  const { addToCart } = useCart();
  const [imgSrc, setImgSrc] = useState<string>("/placeholder.svg");

  useEffect(() => {
    if (deal) {
      setImgSrc(
        formatImageUrl(
          deal.image_url ||
          (deal.image ? deal.image : "https://lh3.googleusercontent.com/aida-public/AB6AXuCuEZkhQLBvJUd2tKiM1YXdA3qHGqfoC1gOJ_5TqdJRzg7iRIg-0h3LZ4jopXxdRwV5H1_yryNObHo7djUIO6S0_42grlXucu8hJTcyp5f6kLXKCpKUjKQ6tOnNKNS5VwI5tTae84KBLGKSh7CqivtV3NBTcEuGPbaYT-2_QAScX9W6AxQ0O2MRjN8linJ33YO9g15jPy5se-Daf1ffgopzI-wyzmlJotp_Z75g1RUP_IeoZf0XJtiL6g")
        )
      );
    }
  }, [deal]);

  // Countdown timer state (seconds remaining)
  const [timeLeft, setTimeLeft] = useState({
    days: 120,
    hours: 20,
    minutes: 36,
    seconds: 48,
  });

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev.seconds > 0) {
          return { ...prev, seconds: prev.seconds - 1 };
        } else if (prev.minutes > 0) {
          return { ...prev, minutes: prev.minutes - 1, seconds: 59 };
        } else if (prev.hours > 0) {
          return { ...prev, hours: prev.hours - 1, minutes: 59, seconds: 59 };
        } else if (prev.days > 0) {
          return { ...prev, days: prev.days - 1, hours: 23, minutes: 59, seconds: 59 };
        }
        return prev;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  if (!deal) return null;

  const discountPercent =
    deal.discount_percent ||
    (deal.old_price && parseFloat(deal.old_price.toString()) > parseFloat(deal.price.toString())
      ? Math.round(
          ((parseFloat(deal.old_price.toString()) - parseFloat(deal.price.toString())) /
            parseFloat(deal.old_price.toString())) *
            100
        )
      : 49);

  return (
    <div id="hot-deals" className="bg-surface rounded-lg border border-line p-4 shadow-sm transition-colors duration-200">
      {/* Widget Header */}
      <div className="flex items-center justify-between border-b border-line pb-2.5 mb-3">
        <h3 className="font-bold text-xs uppercase tracking-wider text-ink">HOT DEALS</h3>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="w-5 h-5 bg-surface-alt hover:bg-surface-sunken text-ink-muted rounded flex items-center justify-center transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">chevron_left</span>
          </button>
          <button
            type="button"
            className="w-5 h-5 bg-surface-alt hover:bg-surface-sunken text-ink-muted rounded flex items-center justify-center transition-colors"
          >
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          </button>
        </div>
      </div>

      {/* Deal Image Container with Discount Badge */}
      <div className="relative bg-surface-alt rounded-lg overflow-hidden mb-3 aspect-[4/3] flex items-center justify-center">
        <Image
          src={imgSrc}
          alt={deal.name}
          fill
          sizes="(max-width: 768px) 100vw, 280px"
          onError={() => setImgSrc("/placeholder.svg")}
          className="w-full h-full object-cover"
        />
        {discountPercent > 0 && (
          <span className="absolute top-2 right-2 w-10 h-10 rounded-full bg-badge-hot text-white font-bold text-[11px] leading-tight flex flex-col items-center justify-center shadow-md">
            <span>{discountPercent}%</span>
            <span className="text-[9px] font-medium leading-none">OFF</span>
          </span>
        )}
      </div>

      {/* Countdown Timer Display */}
      <div className="grid grid-cols-4 gap-1.5 mb-3 text-center">
        <div className="bg-surface-alt/90 rounded py-1 border border-line">
          <div className="font-bold text-xs text-ink">{timeLeft.days}</div>
          <div className="text-[9px] uppercase tracking-wider text-ink-muted font-medium">Days</div>
        </div>
        <div className="bg-surface-alt/90 rounded py-1 border border-line">
          <div className="font-bold text-xs text-ink">{String(timeLeft.hours).padStart(2, "0")}</div>
          <div className="text-[9px] uppercase tracking-wider text-ink-muted font-medium">Hrs</div>
        </div>
        <div className="bg-surface-alt/90 rounded py-1 border border-line">
          <div className="font-bold text-xs text-ink">{String(timeLeft.minutes).padStart(2, "0")}</div>
          <div className="text-[9px] uppercase tracking-wider text-ink-muted font-medium">Mins</div>
        </div>
        <div className="bg-surface-alt/90 rounded py-1 border border-line">
          <div className="font-bold text-xs text-ink">{String(timeLeft.seconds).padStart(2, "0")}</div>
          <div className="text-[9px] uppercase tracking-wider text-ink-muted font-medium">Secs</div>
        </div>
      </div>

      {/* Deal Details */}
      <div className="text-center">
        <Link
          href={`/product/${deal.slug}`}
          className="font-semibold text-sm text-ink hover:text-primary line-clamp-1 transition-colors"
        >
          {deal.name}
        </Link>
        <div className="flex items-center justify-center gap-1 my-1">
          <StarRating rating={deal.average_rating ?? 0} size={14} />
          {(deal.review_count ?? 0) > 0 && (
            <span className="text-[11px] text-ink-muted">({deal.review_count})</span>
          )}
        </div>
        <div className="flex items-center justify-center gap-2 mb-3">
          <span className="text-base font-bold text-primary">৳{deal.price}</span>
          {deal.old_price && (
            <span className="text-xs text-price-old line-through">৳{deal.old_price}</span>
          )}
        </div>

        {/* Action Button with Cart Icon */}
        <div className="flex rounded-md overflow-hidden shadow-sm">
          <div className="bg-accent px-2.5 py-1.5 flex items-center justify-center text-on-accent">
            <span className="material-symbols-outlined text-[16px]">shopping_cart</span>
          </div>
          <button
            onClick={() => addToCart(deal, 1)}
            type="button"
            className="flex-1 bg-primary hover:bg-primary-hover text-on-primary text-xs font-semibold py-1.5 px-3 transition-colors text-center uppercase tracking-wider cursor-pointer"
          >
            Add to cart
          </button>
        </div>
      </div>
    </div>
  );
}
