"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getManagementRoleLabel } from "@/lib/admin-auth";

export default function AdminHeader({
  onMenuToggle,
}: {
  onMenuToggle: () => void;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [showUserMenu, setShowUserMenu] = useState(false);

  const roleLabel = getManagementRoleLabel(user);

  const handleLogout = () => {
    logout();
    router.push("/admin/login");
  };

  return (
    <header className="sticky top-0 z-30 h-16 bg-surface/80 backdrop-blur-md border-b border-line flex items-center justify-between px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuToggle}
          className="lg:hidden text-ink p-1.5 rounded-lg hover:bg-surface-alt transition-colors cursor-pointer"
          aria-label="Open navigation menu"
        >
          <span className="material-symbols-outlined text-[24px]">menu</span>
        </button>
        <div className="flex items-center gap-2.5">
          <span className="text-sm font-bold text-ink">
            Management Portal
          </span>
          <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-md bg-primary/15 text-primary border border-primary/20">
            {roleLabel}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Public Storefront Link */}
        <Link
          href="/"
          target="_blank"
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-ink-muted hover:text-ink hover:bg-surface-alt border border-line transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">visibility</span>
          <span>Storefront</span>
        </Link>

        {/* User Account Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-surface-alt transition-colors cursor-pointer"
          >
            <div className="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center font-bold text-xs uppercase border border-primary/20">
              {(user?.first_name?.[0] || user?.username?.[0] || "A").toUpperCase()}
            </div>
            <div className="hidden md:flex flex-col text-left">
              <span className="text-xs font-bold text-ink line-clamp-1 leading-tight">
                {user?.first_name
                  ? `${user.first_name} ${user.last_name || ""}`.trim()
                  : user?.username || "Admin"}
              </span>
              <span className="text-[10px] text-ink-muted line-clamp-1">
                {user?.email}
              </span>
            </div>
            <span className="material-symbols-outlined text-[16px] text-ink-muted">
              expand_more
            </span>
          </button>

          {showUserMenu && (
            <div
              className="absolute right-0 mt-2 w-56 bg-surface rounded-xl shadow-lg border border-line py-1 z-50 animate-in fade-in zoom-in-95 duration-100"
              onMouseLeave={() => setShowUserMenu(false)}
            >
              <div className="px-4 py-2 border-b border-line md:hidden">
                <p className="text-xs font-bold text-ink">
                  {user?.first_name ? `${user.first_name} ${user.last_name}` : user?.username}
                </p>
                <p className="text-[10px] text-ink-muted truncate">{user?.email}</p>
                <p className="text-[10px] font-bold text-primary mt-1">{roleLabel}</p>
              </div>

              <div className="px-4 py-2 border-b border-line">
                <span className="text-[10px] uppercase font-bold tracking-wider text-ink-muted">
                  Assigned Roles
                </span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(user?.roles || ["ADMINISTRATOR"]).map((r) => (
                    <span
                      key={r}
                      className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-surface-alt text-ink"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-red-600 hover:bg-red-500/10 transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">logout</span>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
