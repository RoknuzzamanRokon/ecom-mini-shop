"use client";

import React from "react";

export default function PerksBar() {
  return (
    <div className="bg-primary text-on-primary rounded-lg overflow-hidden grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-white/20 text-center py-3 px-4 shadow-sm transition-colors duration-200">
      <div className="flex flex-col items-center justify-center p-2">
        <span className="text-xs font-bold uppercase tracking-wider">MONEY BACK</span>
        <span className="text-[11px] opacity-85">30 Days Money Back Guarantee</span>
      </div>
      <div className="flex flex-col items-center justify-center p-2">
        <span className="text-xs font-bold uppercase tracking-wider">FREE SHIPPING</span>
        <span className="text-[11px] opacity-85">Shipping on orders over ৳99</span>
      </div>
      <div className="flex flex-col items-center justify-center p-2">
        <span className="text-xs font-bold uppercase tracking-wider">SPECIAL SALE</span>
        <span className="text-[11px] opacity-85">Extra ৳5 off on all items</span>
      </div>
    </div>
  );
}
