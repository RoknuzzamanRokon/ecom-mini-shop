"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { HotDeal } from "@/lib/types";
import { useCart } from "@/context/CartContext";
import { formatImageUrl } from "@/lib/api";
import StarRating from "@/components/reviews/StarRating";

interface HotDealWidgetProps {
  deal: HotDeal | null;
}

/**
 * The deal's real discount: the API's figure, else one worked out from the
 * prices, else 0. Never an invented one (BUG-085).
 */
export function dealDiscountPercent(deal: HotDeal): number {
  if (typeof deal.discount_percent === "number") return Math.max(0, deal.discount_percent);
  const price = parseFloat(String(deal.price));
  const oldPrice = deal.old_price != null ? parseFloat(String(deal.old_price)) : NaN;
  if (!(oldPrice > price) || !(price >= 0)) return 0;
  return Math.round(((oldPrice - price) / oldPrice) * 100);
}

/** Days, hours, minutes and seconds left until `endsAt`, or null once it has passed. */
export function timeLeftUntil(endsAt: number, now: number) {
  const totalSeconds = Math.floor((endsAt - now) / 1000);
  if (!(totalSeconds > 0)) return null;
  return {
    days: Math.floor(totalSeconds / 86400),
    hours: Math.floor((totalSeconds % 86400) / 3600),
    minutes: Math.floor((totalSeconds % 3600) / 60),
    seconds: totalSeconds % 60,
  };
}

/** The current time, ticking each second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
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

  // The countdown runs only to a real end time from the API (BUG-085).
  const endsAt = deal?.deal_ends_at ? Date.parse(deal.deal_ends_at) : NaN;
  const hasDeadline = Number.isFinite(endsAt);
  const now = useNow(hasDeadline);

  if (!deal) return null;

  const discountPercent = dealDiscountPercent(deal);
  const timeLeft = hasDeadline ? timeLeftUntil(endsAt, now) : null;

  return (
    <div id="hot-deals" className="bg-surface rounded-lg border border-line p-4 shadow-sm transition-colors duration-200">
      {/* Widget Header */}
      {/* One deal at a time, so there is nothing to page through. */}
      <div className="border-b border-line pb-2.5 mb-3">
        <h3 className="font-bold text-xs uppercase tracking-wider text-ink">HOT DEALS</h3>
      </div>

      {/* Deal Image Container with Discount Badge */}
      <Link
        href={`/product/${deal.slug}`}
        className="relative bg-surface-alt rounded-lg overflow-hidden mb-3 aspect-[4/3] flex items-center justify-center"
      >
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
      </Link>

      {/* Countdown to the deal's real end time, when the API gives one */}
      {timeLeft && (
        <div role="timer" aria-label="Time left in this deal" className="grid grid-cols-4 gap-1.5 mb-3 text-center">
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
      )}

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
          {discountPercent > 0 && (
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
