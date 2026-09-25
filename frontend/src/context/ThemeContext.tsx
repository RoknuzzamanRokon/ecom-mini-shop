"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export interface ThemeOption {
  id: string;
  name: string;
  subtitle: string;
  swatches: string[];
}

export const THEMES: ThemeOption[] = [
  {
    id: "ai",
    name: "Kachi Indigo",
    subtitle: "Refined indigo dye on unbleached Kinari cotton",
    swatches: ["#21486B", "#BA8630", "#101F2E", "#A5273D"],
  },
  {
    id: "sumi",
    name: "Sumi & Seal",
    subtitle: "Ink wash on artisanal washi with vermilion seal",
    swatches: ["#262019", "#A83A18", "#342C23", "#7E2B3D"],
  },
  {
    id: "matsu",
    name: "Tokiwa Pine",
    subtitle: "Evergreen pine and aged brass gold",
    swatches: ["#2E5E49", "#B07C22", "#1D4234", "#A82A38"],
  },
  {
    id: "den",
    name: "Signal Graphite",
    subtitle: "Engineered slate grey with electric cyan pulse",
    swatches: ["#1D2A36", "#00B3CC", "#0E141C", "#C81E3C"],
  },
  {
    id: "current",
    name: "Original Classic",
    subtitle: "The original bright blue & amber gold palette",
    swatches: ["#2563EB", "#FBBF24", "#1D4ED8", "#E11D48"],
  },
  {
    id: "oxblood",
    name: "Oxblood Ring",
    subtitle: "Oxblood beads on a charcoal wire, soft rose-grey ground",
    swatches: ["#8E1518", "#767676", "#1A1A1A", "#C0181C"],
  },
  {
    id: "krishnachura",
    name: "Krishnachura Bloom",
    subtitle: "Flame-tree blossom and marigold with monsoon-leaf jade",
    swatches: ["#B83800", "#00A070", "#FFC53D", "#C8175D"],
  },
  {
    id: "lagoon",
    name: "Coral Lagoon",
    subtitle: "Sunlit turquoise shallows over a hot coral reef",
    swatches: ["#007672", "#F55A45", "#003A45", "#D1224F"],
  },
  {
    id: "shapla",
    name: "Shapla Pop",
    subtitle: "Water-lily magenta with a splash of pond turquoise",
    swatches: ["#C20C77", "#0098A6", "#6A0743", "#D4123F"],
  },
  {
    id: "ultraviolet",
    name: "Ultraviolet Spark",
    subtitle: "Deep ultraviolet glow with a hot tangerine spark",
    swatches: ["#7424EC", "#F05A0A", "#420E9C", "#D1146A"],
  },
  {
    id: "kiwi",
    name: "Kiwi & Guava",
    subtitle: "Emerald kiwi and lime flesh with a hot-pink guava pop",
    swatches: ["#007535", "#FF3F8E", "#9EDB45", "#CC0F62"],
  },
];

interface ThemeContextType {
  theme: string;
  isDark: boolean;
  setTheme: (themeId: string) => void;
  toggleDarkMode: () => void;
  setDarkMode: (dark: boolean) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<string>("ai");
  const [isDark, setIsDark] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem("minishop-theme") || "ai";
      const savedDark = localStorage.getItem("minishop-dark") === "1";
      setThemeState(savedTheme);
      setIsDark(savedDark);
      document.documentElement.setAttribute("data-theme", savedTheme);
      if (savedDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    } catch {
      document.documentElement.setAttribute("data-theme", "ai");
    }
    setMounted(true);
  }, []);

  const setTheme = (newTheme: string) => {
    setThemeState(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    try {
      localStorage.setItem("minishop-theme", newTheme);
    } catch {}
  };

  const setDarkMode = (dark: boolean) => {
    setIsDark(dark);
    if (dark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    try {
      localStorage.setItem("minishop-dark", dark ? "1" : "0");
    } catch {}
  };

  const toggleDarkMode = () => {
    setDarkMode(!isDark);
  };

  return (
    <ThemeContext.Provider
      value={{
        theme,
        isDark,
        setTheme,
        toggleDarkMode,
        setDarkMode,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
