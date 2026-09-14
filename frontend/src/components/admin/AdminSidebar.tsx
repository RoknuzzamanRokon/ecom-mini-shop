"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  getAccessibleNavSections,
  type AdminNavItem,
} from "@/lib/admin-navigation";

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

  /**
   * Menu visibility is permission-driven: getAccessibleNavSections filters every
   * item against the permissions on the authenticated user and drops sections
   * left empty. Role names are never consulted for visibility.
   *
   * Seeing a menu entry only means the user may OPEN that module. Whether the
   * actions inside it (approve, suspend, refund…) are offered is a separate,
   * finer-grained check each module makes — and the backend enforces regardless.
   */
  const sections = React.useMemo(
    () => getAccessibleNavSections(user),
    [user]
  );

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden backdrop-blur-xs"
        />
      )}

      <aside
        aria-label="Management navigation"
        className={`fixed top-0 bottom-0 left-0 z-40 w-64 bg-surface border-r border-line flex flex-col justify-between transition-transform duration-200 lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col min-h-0 flex-1">
          {/* Brand Header */}
          <div className="h-16 shrink-0 flex items-center justify-between px-6 border-b border-line">
            <Link href="/admin" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary font-black text-base shadow-xs">
                <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                  admin_panel_settings
                </span>
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
                className="lg:hidden text-ink-muted hover:text-ink p-1 rounded-md cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                aria-label="Close sidebar"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
                  close
                </span>
              </button>
            )}
          </div>

          {/* Permission-filtered navigation */}
          <nav aria-label="Management modules" className="p-4 space-y-4 overflow-y-auto flex-1">
            {sections.map((group) => (
              <div key={group.section} className="space-y-1.5">
                <div className="px-3 pb-1 pt-1">
                  <span className="text-[10px] uppercase font-bold tracking-wider text-ink-muted">
                    {group.section}
                  </span>
                </div>

                {group.items.map((item) => {
                  const active = isLinkActive(item);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      aria-current={active ? "page" : undefined}
                      title={item.description}
                      className={`flex items-center justify-between px-3 py-2.5 rounded-xl font-medium text-xs transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                        active
                          ? "bg-primary text-on-primary shadow-xs font-bold"
                          : "text-ink hover:bg-surface-alt hover:text-ink"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          aria-hidden="true"
                          className={`material-symbols-outlined text-[20px] shrink-0 ${
                            active ? "text-on-primary" : "text-ink-muted"
                          }`}
                        >
                          {item.icon}
                        </span>
                        <span className="truncate">{item.label}</span>
                      </div>
                      {item.badge && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-accent/20 text-accent shrink-0">
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>
        </div>

        {/* Footer Navigation: Return to storefront */}
        <div className="p-4 shrink-0 border-t border-line">
          <Link
            href="/"
            target="_blank"
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-alt transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
              store
            </span>
            <span>View Public Store</span>
          </Link>
        </div>
      </aside>
    </>
  );
}
