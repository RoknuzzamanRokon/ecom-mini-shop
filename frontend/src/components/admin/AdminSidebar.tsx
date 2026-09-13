"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { hasManagementPermission } from "@/lib/admin-auth";

interface AdminNavItem {
  href: string;
  label: string;
  icon: string;
  exact?: boolean;
  requiredPermissions?: string[];
  badge?: string;
}

const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  {
    href: "/admin",
    label: "Dashboard",
    icon: "dashboard",
    exact: true,
  },
  {
    href: "/admin/shops",
    label: "Shops",
    icon: "storefront",
    requiredPermissions: ["shops.admin.manage", "shops.view", "shop:read", "shops:read"],
  },
  {
    href: "/admin/sellers",
    label: "Sellers",
    icon: "badge",
    requiredPermissions: ["sellers.admin.manage", "sellers.view", "seller:read", "sellers:read"],
  },
  {
    href: "/admin/orders",
    label: "Orders",
    icon: "receipt_long",
    requiredPermissions: ["orders.staff.view", "orders.view", "order:read", "orders:read"],
  },
  {
    href: "/admin/payments",
    label: "Payments",
    icon: "payments",
    requiredPermissions: ["payments.view", "payments.verify", "payment:read", "payments:read"],
  },
  {
    href: "/admin/categories",
    label: "Categories",
    icon: "category",
    requiredPermissions: ["categories.admin.manage", "category:read", "categories:read"],
  },
  {
    href: "/admin/audit-logs",
    label: "Audit Logs",
    icon: "history",
    requiredPermissions: ["audit:read", "audit.view", "audit.read"],
  },
];

export default function AdminSidebar({
  isOpen,
  onClose,
}: {
  isOpen?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const { user } = useAuth();

  const isLinkActive = (item: AdminNavItem) => {
    if (item.exact) return pathname === item.href;
    return pathname.startsWith(item.href);
  };

  // Filter items based on user's active permissions
  const accessibleItems = ADMIN_NAV_ITEMS.filter((item) => {
    if (!item.requiredPermissions) return true;
    return hasManagementPermission(user, item.requiredPermissions);
  });

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
            <Link href="/admin" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary font-black text-base shadow-xs">
                <span className="material-symbols-outlined text-[18px]">admin_panel_settings</span>
              </div>
              <div className="flex flex-col">
                <span className="font-extrabold text-sm tracking-tight text-ink">
                  MiniShop
                </span>
                <span className="text-[10px] uppercase font-bold tracking-widest text-primary">
                  Management
                </span>
              </div>
            </Link>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="lg:hidden text-ink-muted hover:text-ink p-1 rounded-md cursor-pointer"
                aria-label="Close sidebar"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            )}
          </div>

          {/* Navigation Links */}
          <nav className="p-4 space-y-1.5 overflow-y-auto max-h-[calc(100vh-140px)]">
            <div className="px-3 pb-2 pt-1">
              <span className="text-[10px] uppercase font-bold tracking-wider text-ink-muted">
                Operations
              </span>
            </div>
            {accessibleItems.map((item) => {
              const active = isLinkActive(item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-xl font-medium text-xs transition-all ${
                    active
                      ? "bg-primary text-on-primary shadow-xs font-bold"
                      : "text-ink hover:bg-surface-alt hover:text-ink"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`material-symbols-outlined text-[20px] ${
                        active ? "text-on-primary" : "text-ink-muted"
                      }`}
                    >
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-accent/20 text-accent">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer Navigation: Return to storefront */}
        <div className="p-4 border-t border-line">
          <Link
            href="/"
            target="_blank"
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">store</span>
            <span>View Public Store</span>
          </Link>
        </div>
      </aside>
    </>
  );
}
