"use client";

import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { useAuth } from "@/context/AuthContext";
import { useProfile } from "@/context/ProfileContext";
import { formatImageUrl, getSupportUnreadCount } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { SUPPORT_UNREAD_EVENT, canUseSupport } from "@/lib/support";

const SUPPORT_HREF = "/profile/support";

const NAV_ITEMS = [
  { href: "/profile/settings", label: "Settings", icon: "settings", hint: "Photo, details & password" },
  { href: "/profile/track", label: "Current Orders", icon: "local_shipping", hint: "Track active deliveries" },
  { href: "/profile/orders", label: "Order History", icon: "receipt_long", hint: "Every order you placed" },
  { href: "/profile/favorites", label: "Favorites", icon: "favorite", hint: "Products you saved" },
  { href: "/profile/reviews", label: "My Reviews", icon: "reviews", hint: "Ratings you have written" },
  { href: "/profile/addresses", label: "Addresses", icon: "location_on", hint: "Delivery locations" },
  { href: SUPPORT_HREF, label: "Support", icon: "support_agent", hint: "Get help with a problem" },
];

export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const { profile } = useProfile();
  const router = useRouter();
  const pathname = usePathname();
  const [supportUnread, setSupportUnread] = useState(0);

  const supportAllowed = canUseSupport(user);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      // Come back here after logging in (a "Contact Support" link, for example).
      const here = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(here)}`);
    }
  }, [isLoading, isAuthenticated, router]);

  // A ticket page announces when it has marked replies read; the count below
  // re-runs, and its cleanup drops any older answer still in flight.
  const [unreadCheck, setUnreadCheck] = useState(0);
  useEffect(() => {
    const recount = () => setUnreadCheck((n) => n + 1);
    window.addEventListener(SUPPORT_UNREAD_EVENT, recount);
    return () => window.removeEventListener(SUPPORT_UNREAD_EVENT, recount);
  }, []);

  // Refreshed on every profile navigation too.
  useEffect(() => {
    const token = getAuthToken();
    if (!isAuthenticated || !supportAllowed || !token) return;
    let cancelled = false;
    getSupportUnreadCount(token)
      .then((count) => {
        if (!cancelled) setSupportUnread(count);
      })
      .catch(() => {
        if (!cancelled) setSupportUnread(0);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, supportAllowed, pathname, unreadCheck]);

  const navItems = supportAllowed ? NAV_ITEMS : NAV_ITEMS.filter((item) => item.href !== SUPPORT_HREF);

  // Below lg the nav is one sideways-scrolling row; bring the current item into
  // view (Support, at the end, would otherwise be off-screen on phones). Sets
  // scrollLeft on the row only, so the page itself never jumps.
  const navRowRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const row = navRowRef.current;
    const active = row?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!row || !active || row.scrollWidth <= row.clientWidth) return;
    row.scrollLeft = active.offsetLeft - (row.clientWidth - active.offsetWidth) / 2;
  }, [pathname, isLoading, isAuthenticated, supportAllowed]);

  const displayName =
    profile?.display_name ||
    (user?.first_name && user?.last_name
      ? `${user.first_name} ${user.last_name}`
      : user?.username) ||
    "My Account";

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-6 flex-1 w-full flex flex-col gap-6">
        <nav className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/" className="hover:text-primary transition-colors">
            Home
          </Link>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          <span className="text-ink font-medium">My Account</span>
        </nav>

        {isLoading || !isAuthenticated ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <span className="material-symbols-outlined text-[48px] text-ink-muted/50 animate-pulse">
              account_circle
            </span>
            <p className="text-sm text-ink-body mt-2">Loading your account…</p>
          </div>
        ) : (
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Sidebar */}
            <aside className="lg:w-64 shrink-0 flex flex-col gap-4">
              <div className="bg-surface rounded-2xl border border-line shadow-sm p-4 flex items-center gap-3">
                <div className="w-14 h-14 rounded-full overflow-hidden bg-surface-alt border border-line flex items-center justify-center shrink-0">
                  {profile?.avatar ? (
                    <Image
                      src={formatImageUrl(profile.avatar)}
                      alt={displayName}
                      width={56}
                      height={56}
                      className="object-cover w-full h-full"
                    />
                  ) : (
                    <span className="text-lg font-bold text-primary">
                      {displayName.charAt(0).toUpperCase()}
                    </span>
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-ink truncate">{displayName}</p>
                  <p className="text-xs text-ink-muted truncate">{user?.email}</p>
                </div>
              </div>

              <div
                ref={navRowRef}
                className="relative bg-surface rounded-2xl border border-line shadow-sm p-2 flex lg:flex-col gap-1 overflow-x-auto"
              >
                {navItems.map((item) => {
                  // Prefix match, so /profile/orders/<n> and /profile/support/<n> stay lit.
                  const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const badge = item.href === SUPPORT_HREF ? supportUnread : 0;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={isActive ? "page" : undefined}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors shrink-0 ${
                        isActive
                          ? "bg-primary text-on-primary font-bold shadow-sm"
                          : "text-ink hover:bg-surface-alt font-medium"
                      }`}
                    >
                      <span className="material-symbols-outlined text-[20px] shrink-0">
                        {item.icon}
                      </span>
                      <span className="flex flex-col min-w-0">
                        <span className="truncate">{item.label}</span>
                        <span
                          className={`hidden lg:block text-[11px] font-normal truncate ${
                            isActive ? "text-on-primary/75" : "text-ink-muted"
                          }`}
                        >
                          {item.hint}
                        </span>
                      </span>
                      {badge > 0 && (
                        <span
                          className={`ml-auto min-w-5 h-5 px-1.5 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0 ${
                            isActive ? "bg-on-primary text-primary" : "bg-accent text-on-accent"
                          }`}
                        >
                          {badge}
                          <span className="sr-only"> {badge === 1 ? "ticket" : "tickets"} with a new reply</span>
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </aside>

            {/* Content */}
            <section className="flex-1 min-w-0">{children}</section>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
