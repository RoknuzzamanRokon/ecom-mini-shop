"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import Image from "next/image";

interface ProductImageZoomProps {
  src: string;
  alt: string;
  badge?: string;
  fallbackSrc?: string;
}

export default function ProductImageZoom({
  src,
  alt,
  badge,
  fallbackSrc = "/placeholder.svg",
}: ProductImageZoomProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isZooming, setIsZooming] = useState(false);
  const [coords, setCoords] = useState({ x: 0, y: 0, xPercent: 50, yPercent: 50 });
  const [currentSrc, setCurrentSrc] = useState(src);

  useEffect(() => {
    setCurrentSrc(src);
  }, [src]);

  const LENS_SIZE = 180; // Diameter of circular magnifying loupe
  const ZOOM_FACTOR = 2.6; // 2.6x zoom level

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const clampedX = Math.max(0, Math.min(x, rect.width));
    const clampedY = Math.max(0, Math.min(y, rect.height));

    const xPercent = (clampedX / rect.width) * 100;
    const yPercent = (clampedY / rect.height) * 100;

    const lensLeft = Math.max(0, Math.min(clampedX - LENS_SIZE / 2, rect.width - LENS_SIZE));
    const lensTop = Math.max(0, Math.min(clampedY - LENS_SIZE / 2, rect.height - LENS_SIZE));

    setCoords({
      x: lensLeft,
      y: lensTop,
      xPercent,
      yPercent,
    });
  }, []);

  return (
    <div
      ref={containerRef}
      onMouseEnter={() => setIsZooming(true)}
      onMouseLeave={() => setIsZooming(false)}
      onMouseMove={handleMouseMove}
      className="relative aspect-[4/3] sm:aspect-square max-h-[430px] w-full bg-surface-alt/70 rounded-xl overflow-hidden border border-line cursor-crosshair shadow-inner select-none transition-all"
    >
      {/* Base Image */}
      <Image
        src={currentSrc}
        alt={alt}
        fill
        sizes="(max-width: 768px) 100vw, 45vw"
        priority
        unoptimized
        onError={() => setCurrentSrc(fallbackSrc)}
        className="object-cover object-center transition-transform duration-200"
      />

      {/* Product Badge if present */}
      {badge && (
        <span className="absolute top-3 right-3 bg-badge-hot text-white text-xs font-bold px-3 py-1 rounded-full uppercase shadow-sm z-10 pointer-events-none">
          {badge}
        </span>
      )}

      {/* Amazon-style Circular Magnifying Glass Loupe */}
      {isZooming && (
        <div
          className="absolute pointer-events-none rounded-full border-2 border-white shadow-[0_4px_25px_rgba(0,0,0,0.35),0_0_0_1px_rgba(0,0,0,0.1)] z-20 overflow-hidden ring-2 ring-primary/40"
          style={{
            width: `${LENS_SIZE}px`,
            height: `${LENS_SIZE}px`,
            left: `${coords.x}px`,
            top: `${coords.y}px`,
            backgroundImage: `url(${currentSrc})`,
            backgroundRepeat: "no-repeat",
            backgroundSize: `${ZOOM_FACTOR * 100}%`,
            backgroundPosition: `${coords.xPercent}% ${coords.yPercent}%`,
          }}
        >
          {/* Subtle glass reflection highlight */}
          <div className="w-full h-full rounded-full bg-gradient-to-tr from-white/0 via-white/10 to-white/20 pointer-events-none" />
        </div>
      )}

      {/* Zoom indicator hint (fades when zooming) */}
      <div
        className={`absolute bottom-3 right-3 bg-surface/90 text-ink text-[11px] font-semibold px-2.5 py-1 rounded-md border border-line shadow-xs flex items-center gap-1.5 pointer-events-none transition-opacity duration-200 ${
          isZooming ? "opacity-0" : "opacity-85"
        }`}
      >
        <span className="material-symbols-outlined text-[15px] text-primary">zoom_in</span>
        <span>Hover to zoom</span>
      </div>
    </div>
  );
}
