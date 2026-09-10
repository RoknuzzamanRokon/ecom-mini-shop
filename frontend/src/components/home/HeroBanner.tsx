"use client";

import React from "react";
import Image from "next/image";

export default function HeroBanner() {
  return (
    <div className="bg-surface rounded-lg border border-line overflow-hidden shadow-sm transition-colors duration-200">
      <div className="relative bg-gradient-to-r from-surface-alt via-surface to-surface-alt/40 min-h-[260px] sm:min-h-[300px] flex items-center">
        {/* Left Text Content */}
        <div className="w-full sm:w-3/5 p-6 sm:p-10 z-10">
          <span className="text-xs uppercase font-bold tracking-widest text-ink-muted">
            SPRING 2025
          </span>
          <h2 className="text-2xl sm:text-4xl font-extrabold text-ink tracking-tight mt-1 mb-2">
            WOMEN <span className="text-accent">FASHION</span>
          </h2>
          <p className="text-xs sm:text-sm text-ink-body max-w-md line-clamp-2 mb-5">
            Carefully curated essentials designed for everyday comfort, timeless modern silhouettes,
            and architectural elegance.
          </p>
          <a
            href="#products-section"
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded shadow-sm transition-all hover:shadow cursor-pointer"
          >
            <span>SHOP NOW</span>
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </a>
        </div>

        {/* Right Hero Imagery */}
        <div className="hidden sm:block absolute right-0 bottom-0 top-0 w-2/5 overflow-hidden">
          <Image
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuCSVwxG52Hz7vhpEWeXPi5UJm20e7TlgZtWZbHszLI4cifI7F5uPYFbxEy59NIlYWIUigqpNJ2egy32cewdQGxDTxh8kV6bZ4Nf3w3s4jW6RW8lR0YCkvt9InRkL9IWpB-tIKgwd5-gZ27tVGExSWYVzPjmxSQkjJsfrPKBicGIs9IV5ytAnf5usn6PU6lCg0h8tocx1ADCxwNN9AUQJhhhCJ3zCib2ZZadlDXWecBkEWqBrt2ESFdvQQ"
            alt="Banner Feature"
            fill
            sizes="40vw"
            className="w-full h-full object-cover object-center mix-blend-multiply opacity-85"
            priority
          />
        </div>
      </div>
    </div>
  );
}
