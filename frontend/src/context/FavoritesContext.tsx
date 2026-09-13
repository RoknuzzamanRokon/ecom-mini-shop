"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Favorite } from "@/lib/types";
import { addFavorite, getFavorites, removeFavorite } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { useAuth } from "./AuthContext";

interface FavoritesContextType {
  favorites: Favorite[];
  favoriteIds: Set<number>;
  isLoading: boolean;
  isFavorite: (productId: number) => boolean;
  toggleFavorite: (productId: number) => Promise<void>;
  refresh: () => Promise<void>;
}

const FavoritesContext = createContext<FavoritesContextType | undefined>(undefined);

export function FavoritesProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setFavorites([]);
      return;
    }
    try {
      setIsLoading(true);
      setFavorites(await getFavorites(token));
    } catch {
      setFavorites([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      refresh();
    } else {
      setFavorites([]);
    }
  }, [isAuthenticated, refresh]);

  const favoriteIds = useMemo(
    () => new Set(favorites.map((f) => f.product.id)),
    [favorites]
  );

  const isFavorite = useCallback(
    (productId: number) => favoriteIds.has(productId),
    [favoriteIds]
  );

  const toggleFavorite = useCallback(
    async (productId: number) => {
      const token = getAuthToken();
      if (!token) return;

      if (favoriteIds.has(productId)) {
        setFavorites((prev) => prev.filter((f) => f.product.id !== productId));
        try {
          await removeFavorite(productId, token);
        } catch {
          await refresh();
        }
        return;
      }

      try {
        const created = await addFavorite(productId, token);
        setFavorites((prev) =>
          prev.some((f) => f.product.id === productId) ? prev : [created, ...prev]
        );
      } catch {
        await refresh();
      }
    },
    [favoriteIds, refresh]
  );

  return (
    <FavoritesContext.Provider
      value={{ favorites, favoriteIds, isLoading, isFavorite, toggleFavorite, refresh }}
    >
      {children}
    </FavoritesContext.Provider>
  );
}

export function useFavorites() {
  const context = useContext(FavoritesContext);
  if (!context) {
    throw new Error("useFavorites must be used within a FavoritesProvider");
  }
  return context;
}
