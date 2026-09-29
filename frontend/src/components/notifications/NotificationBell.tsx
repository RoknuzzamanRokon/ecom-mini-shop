"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";

import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  NOTIFICATION_INBOX_PATHS,
  formatUnreadBadge,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notifyNotificationsChanged,
  type AppNotification,
  type NotificationAudience,
} from "@/lib/notifications";

import NotificationListItem from "./NotificationListItem";
import { useUnreadNotifications } from "./useUnreadNotifications";

const DROPDOWN_SIZE = 10;

/**
 * The header bell (docs/NOTIFICATION_SYSTEM.md §9): an unread badge, and a
 * dropdown with the 10 newest notifications, "Mark all read" and "View all".
 *
 * `tone` matches the header it sits in: "nav" for the storefront's dark bar,
 * "surface" for the Seller Center and Console headers.
 *
 * Keyboard: Enter or Space toggles it, ArrowDown from the bell moves into the
 * list, ArrowUp/ArrowDown move between items, Escape closes it and puts focus
 * back on the bell. A click outside, or leaving the page, closes it too.
 */
export default function NotificationBell({
  audience,
  tone = "surface",
}: {
  audience: NotificationAudience;
  tone?: "nav" | "surface";
}) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { count } = useUnreadNotifications(audience, isAuthenticated);

  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [load, setLoad] = useState(0);
  const [openedAt, setOpenedAt] = useState(pathname);

  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  // Leaving the page closes the dropdown (adjusted during render, not in an effect).
  if (open && openedAt !== pathname) {
    setOpen(false);
    setOpenedAt(pathname);
  }

  // Each opening loads the newest notifications again.
  useEffect(() => {
    const token = getAuthToken();
    if (!open || !token) return;
    let cancelled = false;
    getNotifications(token, audience)
      .then((page) => {
        if (!cancelled) setItems(page.results.slice(0, DROPDOWN_SIZE));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Notifications couldn't be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [open, audience, load]);

  // Close on a click outside.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  if (!isAuthenticated) return null;

  const show = () => {
    setItems(null);
    setError(null);
    setNow(Date.now());
    setOpenedAt(pathname);
    setOpen(true);
  };

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  };

  const retry = () => {
    setItems(null);
    setError(null);
    setLoad((n) => n + 1);
  };

  const focusItem = (step: 1 | -1 | "first") => {
    const nodes = Array.from(panelRef.current?.querySelectorAll<HTMLElement>("[data-notification-item]") ?? []);
    if (nodes.length === 0) return;
    if (step === "first") {
      nodes[0].focus();
      return;
    }
    const current = nodes.indexOf(document.activeElement as HTMLElement);
    nodes[(current + step + nodes.length) % nodes.length].focus();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(document.activeElement === buttonRef.current ? "first" : 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(-1);
    }
  };

  const openNotification = async (notification: AppNotification) => {
    const token = getAuthToken();
    if (token && notification.read_at === null) {
      try {
        await markNotificationRead(token, notification.id);
        notifyNotificationsChanged();
      } catch {
        // Opening it matters more than the dot; the inbox can still mark it.
      }
    }
    close(false);
    if (notification.action_url) router.push(notification.action_url);
  };

  const markAllRead = async () => {
    const token = getAuthToken();
    if (!token) return;
    try {
      await markAllNotificationsRead(token, audience);
      const readAt = new Date().toISOString();
      setItems((current) => current?.map((item) => ({ ...item, read_at: item.read_at ?? readAt })) ?? current);
      notifyNotificationsChanged();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Notifications couldn't be marked as read.");
    }
  };

  const label =
    count === 0 ? "Notifications" : `${count} unread notification${count === 1 ? "" : "s"}`;
  const hasUnread = count > 0 || (items ?? []).some((item) => item.read_at === null);

  return (
    <div className="relative" ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (open ? close(false) : show())}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={label}
        title="Notifications"
        className={clsx(
          "relative flex items-center rounded-full p-1.5 transition-colors cursor-pointer",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
          tone === "nav" ? "text-on-primary hover:bg-white/10" : "text-ink hover:bg-surface-alt"
        )}
      >
        <span aria-hidden="true" className={clsx("material-symbols-outlined text-[24px]", open && "fill-active")}>
          notifications
        </span>
        {count > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-on-primary"
          >
            {formatUnreadBadge(count)}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="region"
          aria-label="Notifications"
          className={clsx(
            "z-50 overflow-hidden rounded-xl border border-line bg-surface text-ink shadow-lg",
            "fixed inset-x-4 top-16 sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:mt-2 sm:w-96"
          )}
        >
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <h2 className="text-sm font-bold text-ink">Notifications</h2>
            <button
              type="button"
              onClick={markAllRead}
              disabled={!hasUnread}
              className="text-xs font-semibold text-primary hover:underline disabled:cursor-default disabled:text-ink-faint disabled:no-underline cursor-pointer"
            >
              Mark all read
            </button>
          </div>

          <div className="max-h-[min(28rem,calc(100vh-10rem))] overflow-y-auto divide-y divide-line-subtle">
            {error ? (
              <div role="alert" className="px-4 py-6 text-center">
                <p className="text-sm text-ink-muted">{error}</p>
                <button
                  type="button"
                  onClick={retry}
                  className="mt-3 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  Try again
                </button>
              </div>
            ) : items === null ? (
              <div role="status" aria-busy="true" className="flex justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-b-2 border-primary" />
                <span className="sr-only">Loading notifications…</span>
              </div>
            ) : items.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <span aria-hidden="true" className="material-symbols-outlined text-[32px] text-ink-faint">
                  notifications_none
                </span>
                <p className="mt-2 text-sm text-ink-muted">You&apos;re all caught up.</p>
              </div>
            ) : (
              items.map((item) => (
                <NotificationListItem key={item.id} notification={item} now={now} onOpen={openNotification} compact />
              ))
            )}
          </div>

          <Link
            href={NOTIFICATION_INBOX_PATHS[audience]}
            onClick={() => close(false)}
            className="block border-t border-line px-4 py-2.5 text-center text-xs font-semibold text-primary hover:bg-surface-alt"
          >
            View all
          </Link>
        </div>
      )}
    </div>
  );
}
