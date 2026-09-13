"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useSeller } from "./SellerGuard";
import { useAuth } from "@/context/AuthContext";

export default function SellerHeader({
  onMenuToggle,
}: {
  onMenuToggle: () => void;
}) {
  const { seller } = useSeller();
  const { user, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);

  return (
    <header className="sticky top-0 z-30 h-16 bg-surface/80 backdrop-blur-md border-b border-line flex items-center justify-between px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuToggle}
          className="lg:hidden text-ink p-1.5 rounded-lg hover:bg-surface-alt transition-colors"
          aria-label="Open navigation menu"
        >
          <span className="material-symbols-outlined text-[24px]">menu</span>
        </button>
        <div className="hidden sm:flex items-center gap-2">
          <span className="text-sm font-bold text-ink">
            {seller?.business_name || "Seller Panel"}
          </span>
          {seller?.seller_type && (
            <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-md bg-accent/15 text-accent border border-accent/20">
              {seller.seller_type_display || seller.seller_type.replace(/_/g, " ")}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Storefront Link */}
        <Link
          href="/"
          target="_blank"
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-ink-muted hover:text-ink hover:bg-surface-alt border border-line transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">visibility</span>
          <span>View Store</span>
        </Link>

        {/* User Account Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-alt transition-colors cursor-pointer"
          >
            <div className="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center font-bold text-xs uppercase border border-primary/20">
              {(user?.first_name?.[0] || user?.username?.[0] || "S").toUpperCase()}
            </div>
            <span className="hidden md:inline text-xs font-bold text-ink max-w-[120px] truncate">
              {user?.username}
            </span>
            <span className="material-symbols-outlined text-[16px] text-ink-muted">
              expand_more
            </span>
          </button>

          {showUserMenu && (
            <div className="absolute right-0 top-full mt-2 w-52 bg-surface rounded-xl shadow-xl border border-line p-1 z-50 animate-in fade-in zoom-in-95 duration-150">
              <div className="px-3 py-2 border-b border-line">
                <p className="text-xs font-bold text-ink truncate">
                  {seller?.business_name || user?.username}
                </p>
                <p className="text-[11px] text-ink-muted truncate">{user?.email}</p>
              </div>
              <div className="py-1">
                <Link
                  href="/seller/profile"
                  onClick={() => setShowUserMenu(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-ink hover:bg-surface-alt transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">badge</span>
                  <span>Seller Profile</span>
                </Link>
                <Link
                  href="/profile"
                  onClick={() => setShowUserMenu(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-ink hover:bg-surface-alt transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">person</span>
                  <span>Customer Profile</span>
                </Link>
                <Link
                  href="/"
                  onClick={() => setShowUserMenu(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-ink hover:bg-surface-alt transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">shopping_bag</span>
                  <span>Storefront</span>
                </Link>
              </div>
              <div className="pt-1 border-t border-line">
                <button
                  type="button"
                  onClick={() => {
                    setShowUserMenu(false);
                    logout();
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold text-accent hover:bg-accent/10 transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[16px]">logout</span>
                  <span>Log Out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
