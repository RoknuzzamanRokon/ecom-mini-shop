"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSeller } from "./SellerGuard";

const NAV_ITEMS = [
  { href: "/seller", label: "Dashboard", icon: "dashboard", exact: true },
  { href: "/seller/shops", label: "My Shops", icon: "storefront" },
  { href: "/seller/products", label: "Products", icon: "inventory_2" },
  { href: "/seller/orders", label: "Orders", icon: "receipt_long" },
  { href: "/seller/wallet", label: "Wallet & Points", icon: "account_balance_wallet" },
  { href: "/seller/profile", label: "Seller Profile", icon: "badge" },
];

export default function SellerSidebar({
  isOpen,
  onClose,
}: {
  isOpen?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const { seller } = useSeller();

  const isLinkActive = (item: (typeof NAV_ITEMS)[0]) => {
    if (item.exact) return pathname === item.href;
    return pathname.startsWith(item.href);
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/50 lg:hidden backdrop-blur-xs"
        />
      )}

      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 w-64 bg-surface border-r border-line flex flex-col justify-between transition-transform duration-200 lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div>
          {/* Brand Header */}
          <div className="h-16 flex items-center justify-between px-6 border-b border-line">
            <Link href="/seller" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary font-black text-base shadow-xs">
                M
              </div>
              <div className="flex flex-col">
                <span className="font-extrabold text-sm tracking-tight text-ink">
                  MiniShop
                </span>
                <span className="text-[10px] uppercase font-bold tracking-widest text-primary">
                  Seller Center
                </span>
              </div>
            </Link>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="lg:hidden text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            )}
          </div>

          {/* Seller Business Info Pill */}
          {seller && (
            <div className="mx-4 my-4 p-3 rounded-xl bg-surface-alt/70 border border-line">
              <p className="text-xs font-bold text-ink truncate">
                {seller.business_name}
              </p>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="inline-block w-2 h-2 rounded-full bg-success"></span>
                <span className="text-[10px] font-semibold text-ink-muted uppercase tracking-wider">
                  {seller.seller_type_display || seller.seller_type}
                </span>
              </div>
            </div>
          )}

          {/* Navigation Links */}
          <nav className="px-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const active = isLinkActive(item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-bold transition-colors ${
                    active
                      ? "bg-primary text-on-primary shadow-xs"
                      : "text-ink-body hover:bg-surface-alt hover:text-ink"
                  }`}
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Bottom Actions: Return to Store & Customer Account */}
        <div className="p-4 border-t border-line space-y-1">
          <Link
            href="/"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">shopping_bag</span>
            <span>Back to Storefront</span>
          </Link>
          <Link
            href="/profile"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">person</span>
            <span>Customer Profile</span>
          </Link>
        </div>
      </aside>
    </>
  );
}
