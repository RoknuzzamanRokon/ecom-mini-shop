"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  NOTIFICATIONS_CHANGED_EVENT,
  getUnreadNotificationCount,
  type NotificationAudience,
} from "@/lib/notifications";

/** How often an open, visible tab re-counts (§3 D3). */
export const UNREAD_POLL_MS = 60_000;

/**
 * The unread count for one inbox, kept fresh the way §9 describes: it
 * re-counts on every navigation, when any part of the page announces that
 * notifications changed, when the tab becomes visible again, and every 60 s
 * while it stays visible. A hidden tab doesn't poll.
 *
 * A failed count keeps the last known number rather than flashing to zero.
 */
export function useUnreadNotifications(
  audience: NotificationAudience,
  enabled = true
): { count: number; refresh: () => void } {
  const { isAuthenticated } = useAuth();
  const pathname = usePathname();
  const active = enabled && isAuthenticated;
  const [count, setCount] = useState(0);
  const [check, setCheck] = useState(0);

  const refresh = useCallback(() => setCheck((n) => n + 1), []);

  useEffect(() => {
    if (!active) return;
    const whenVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    const timer = window.setInterval(whenVisible, UNREAD_POLL_MS);
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, refresh);
    document.addEventListener("visibilitychange", whenVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, refresh);
      document.removeEventListener("visibilitychange", whenVisible);
    };
  }, [active, refresh]);

  useEffect(() => {
    const token = getAuthToken();
    if (!active || !token) return;
    let cancelled = false;
    getUnreadNotificationCount(token, audience)
      .then((unread) => {
        if (!cancelled) setCount(unread);
      })
      .catch(() => {
        // Offline, throttled or signed out mid-poll: keep the last count.
      });
    return () => {
      cancelled = true;
    };
  }, [active, audience, pathname, check]);

  return { count: active ? count : 0, refresh };
}
