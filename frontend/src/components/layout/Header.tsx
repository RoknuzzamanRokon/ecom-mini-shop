"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";

interface HeaderProps {
  onSearch?: (query: string) => void;
  searchQuery?: string;
}

export default function Header({ onSearch, searchQuery = "" }: HeaderProps) {
  const { totalItemsCount, setIsCartOpen } = useCart();
  const { user, isAuthenticated, isLoading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState(searchQuery);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch) {
      onSearch(query);
    }
  };

  const handleLogout = () => {
    logout();
    setIsUserMenuOpen(false);
    router.push("/");
  };

  // Close user menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }
    if (isUserMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isUserMenuOpen]);

  const displayName =
    user?.first_name && user?.last_name
      ? `${user.first_name} ${user.last_name}`
      : user?.username || "Account";

  return (
    <header className="w-full bg-nav text-on-primary transition-colors duration-200">
      {/* Main Header Bar */}
      <div className="max-w-[1360px] mx-auto px-4 sm:px-6 py-2.5 flex items-center justify-between gap-4">
        {/* Logo */}
        <div className="flex items-center gap-3 shrink-0">
          <Link
            href="/"
            className="flex items-center bg-surface px-3 py-1.5 rounded-lg shadow-sm border border-line/40 transition-transform active:scale-98"
          >
            <svg
              fill="none"
              height="32"
              viewBox="0 0 160 40"
              width="130"
              xmlns="http://www.w3.org/2000/svg"
            >
              <rect fill="var(--c-primary)" height="28" rx="8" width="28" x="2" y="6" />
              <path
                d="M10 14h12l-1.5 11h-9L10 14z"
                stroke="var(--c-on-primary)"
                strokeLinejoin="round"
                strokeWidth="2"
              />
              <path
                d="M13 14v-2a3 3 0 0 1 6 0v2"
                stroke="var(--c-on-primary)"
                strokeLinecap="round"
                strokeWidth="2"
              />
              <text
                fill="var(--c-text-strong)"
                fontFamily="Inter, -apple-system, sans-serif"
                fontSize="18"
                fontWeight="800"
                letterSpacing="-0.5px"
                x="38"
                y="26"
              >
                MINISHOP
              </text>
            </svg>
          </Link>
        </div>

        {/* Quick Search Form */}
        <form onSubmit={handleSubmit} className="hidden md:flex flex-1 max-w-xl mx-4">
          <div className="relative w-full flex items-center shadow-inner rounded-md overflow-hidden bg-surface">
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (onSearch) onSearch(e.target.value);
              }}
              placeholder="Search products, brands and categories..."
              className="w-full bg-surface text-ink placeholder-ink-muted text-sm py-2 pl-3.5 pr-10 border-0 focus:outline-none"
            />
            <button
              type="submit"
              className="bg-accent hover:bg-accent-hover text-on-accent px-4 py-2 font-medium text-sm flex items-center justify-center transition-colors"
              title="Search"
            >
              <span className="material-symbols-outlined text-[20px]">search</span>
            </button>
          </div>
        </form>

        {/* Right Utility Actions */}
        <div className="flex items-center gap-4 text-on-primary shrink-0">
          <a
            href="#hot-deals"
            className="hidden sm:flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase bg-primary-deep/40 hover:bg-primary-deep/60 px-2.5 py-1.5 rounded text-accent transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">local_offer</span>
            <span>Today&apos;s Deal</span>
          </a>

          {/* Cart Action */}
          <button
            onClick={() => setIsCartOpen(true)}
            className="relative flex items-center p-1.5 hover:bg-white/10 rounded-full transition-colors focus:outline-none"
            title="Shopping Cart"
            type="button"
          >
            <span className="material-symbols-outlined text-[24px]">shopping_bag</span>
            {totalItemsCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] px-1 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-on-accent animate-pulse">
                {totalItemsCount}
              </span>
            )}
          </button>

          {/* Auth Section */}
          <div className="flex items-center gap-2 pl-2 border-l border-white/20">
            {authLoading ? (
              /* Loading placeholder */
              <div className="w-8 h-8 rounded-full bg-white/20 border border-white/40 flex items-center justify-center animate-pulse">
                <span className="material-symbols-outlined text-[18px]">person</span>
              </div>
            ) : isAuthenticated && user ? (
              /* Authenticated: user menu */
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                  className="flex items-center gap-2 hover:bg-white/10 rounded-lg px-2 py-1 transition-colors focus:outline-none"
                  type="button"
                  title={displayName}
                >
                  <div className="w-8 h-8 rounded-full bg-accent/80 border border-white/40 flex items-center justify-center text-on-accent font-bold text-sm">
                    {(user.first_name?.[0] || user.username[0]).toUpperCase()}
                  </div>
                  <span className="hidden lg:inline text-sm font-medium max-w-[120px] truncate">
                    {displayName}
                  </span>
                  <span className="material-symbols-outlined text-[16px]">
                    {isUserMenuOpen ? "expand_less" : "expand_more"}
                  </span>
                </button>

                {/* Dropdown Menu */}
                {isUserMenuOpen && (
                  <div className="absolute right-0 top-full mt-2 w-56 bg-surface rounded-lg shadow-xl border border-line z-50 overflow-hidden">
                    {/* User info */}
                    <div className="px-4 py-3 border-b border-line">
                      <p className="text-sm font-semibold text-ink truncate">
                        {displayName}
                      </p>
                      <p className="text-xs text-ink-muted truncate">
                        {user.email}
                      </p>
                    </div>

                    {/* Menu items */}
                    <div className="py-1">
                      <button
                        onClick={handleLogout}
                        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-surface-alt transition-colors"
                        type="button"
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          logout
                        </span>
                        Sign Out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* Unauthenticated: Login & Register links */
              <div className="flex items-center gap-1.5">
                <Link
                  href="/login"
                  className="flex items-center gap-1 hover:bg-white/10 rounded-lg px-2.5 py-1.5 transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">login</span>
                  <span className="text-sm font-medium">Login</span>
                </Link>
                <Link
                  href="/register"
                  className="hidden sm:flex items-center gap-1 bg-white/15 hover:bg-white/25 rounded-lg px-2.5 py-1.5 transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">person_add</span>
                  <span className="text-sm font-medium">Register</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

