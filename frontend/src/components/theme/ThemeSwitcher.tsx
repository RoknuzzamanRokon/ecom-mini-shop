"use client";

import React, { useState } from "react";
import { THEMES, useTheme } from "@/context/ThemeContext";

export default function ThemeSwitcher() {
  const [isOpen, setIsOpen] = useState(false);
  const { theme, isDark, setTheme, setDarkMode } = useTheme();

  return (
    <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3">
      {/* Theme Picker Modal Panel */}
      {isOpen && (
        <div
          role="dialog"
          aria-label="Theme selector"
          className="w-[20rem] max-w-[calc(100vw-2.5rem)] rounded-xl border border-line bg-surface shadow-2xl shadow-black/20 overflow-hidden transition-all animate-in fade-in zoom-in-95 duration-150"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-line px-4 py-3 bg-surface-alt/60">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px] text-primary">palette</span>
              <h2 className="text-xs font-bold uppercase tracking-wider text-ink">
                Color Grading &amp; Theme
              </h2>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink cursor-pointer"
              type="button"
              title="Close theme picker"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>

          {/* Theme Palette List */}
          <div className="max-h-[min(26rem,60vh)] overflow-y-auto p-2 space-y-1.5">
            {THEMES.map((t) => {
              const isSelected = theme === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTheme(t.id)}
                  type="button"
                  className={`w-full flex items-start gap-3 p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                    isSelected
                      ? "border-primary bg-surface-alt shadow-xs"
                      : "border-transparent hover:border-line hover:bg-surface-alt/50"
                  }`}
                >
                  {/* Swatches mini preview */}
                  <div className="flex -space-x-1 shrink-0 mt-0.5">
                    {t.swatches.map((color, idx) => (
                      <span
                        key={idx}
                        className="w-4 h-4 rounded-full border border-surface shadow-xs"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-ink truncate">
                        {t.name}
                      </span>
                      {isSelected && (
                        <span className="material-symbols-outlined text-[16px] text-primary">
                          check_circle
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-ink-muted line-clamp-1 mt-0.5">
                      {t.subtitle}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Appearance Light / Dark Toggle */}
          <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 bg-surface-alt/40">
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
              Appearance
            </span>
            <div className="flex overflow-hidden rounded-md border border-line bg-surface" role="group">
              <button
                onClick={() => setDarkMode(false)}
                type="button"
                className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1 ${
                  !isDark
                    ? "bg-primary text-on-primary"
                    : "text-ink-muted hover:text-ink hover:bg-surface-alt"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">light_mode</span>
                <span>Light</span>
              </button>
              <button
                onClick={() => setDarkMode(true)}
                type="button"
                className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1 border-l border-line ${
                  isDark
                    ? "bg-primary text-on-primary"
                    : "text-ink-muted hover:text-ink hover:bg-surface-alt"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">dark_mode</span>
                <span>Dark</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-on-primary shadow-lg shadow-black/25 transition-transform hover:bg-primary-hover active:scale-95 cursor-pointer focus:outline-none"
        title="Change theme & color grading"
        type="button"
      >
        <span className="material-symbols-outlined text-[22px]">palette</span>
      </button>
    </div>
  );
}
