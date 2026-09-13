"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useFavorites } from "@/context/FavoritesContext";

interface FavoriteButtonProps {
  productId: number;
  size?: "sm" | "md";
  className?: string;
}

export default function FavoriteButton({
  productId,
  size = "sm",
  className = "",
}: FavoriteButtonProps) {
  const { isAuthenticated } = useAuth();
  const { isFavorite, toggleFavorite } = useFavorites();
  const router = useRouter();

  const active = isFavorite(productId);
  const iconSize = size === "md" ? "text-[22px]" : "text-[18px]";
  const boxSize = size === "md" ? "w-10 h-10" : "w-8 h-8";

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    toggleFavorite(productId);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      title={active ? "Remove from favorites" : "Add to favorites"}
      aria-label={active ? "Remove from favorites" : "Add to favorites"}
      aria-pressed={active}
      className={`${boxSize} flex items-center justify-center rounded-full bg-surface/90 backdrop-blur-sm border border-line shadow-sm transition-colors cursor-pointer ${
        active ? "text-accent" : "text-ink-muted hover:text-accent"
      } ${className}`}
    >
      <span
        className={`material-symbols-outlined ${iconSize}`}
        style={{ fontVariationSettings: active ? "'FILL' 1" : "'FILL' 0" }}
      >
        favorite
      </span>
    </button>
  );
}
