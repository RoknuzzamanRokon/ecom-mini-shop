"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { getAuthToken } from "@/lib/auth";
import {
  NOTIFICATIONS_CHANGED_EVENT,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notifyNotificationsChanged,
  type AppNotification,
  type NotificationAudience,
} from "@/lib/notifications";

import NotificationListItem from "./NotificationListItem";

type Filter = "all" | "unread";

const INTROS: Record<NotificationAudience, string> = {
  CUSTOMER: "Updates about your orders, payments and support tickets.",
  SELLER: "New orders, decisions on your account, shops and products, stock, reviews and points.",
  STAFF: "Work waiting for you: shops to review and support tickets.",
};

interface Loaded {
  key: string;
  items: AppNotification[];
  next: string | null;
  error: string | null;
}

/**
 * The whole inbox for one audience (docs/NOTIFICATION_SYSTEM.md §9), shared by
 * /profile/notifications, /seller/notifications and /admin/notifications.
 * All or Unread, "Load more" by keyset cursor, and Mark all read. Opening a
 * notification marks it read and follows its link.
 */
export default function NotificationInbox({ audience }: { audience: NotificationAudience }) {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("all");
  const [reload, setReload] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [now, setNow] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // Our own "changed" announcements shouldn't make this page reload itself.
  const announcing = useRef(false);

  const requestKey = `${audience}|${filter}|${reload}`;

  useEffect(() => {
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getNotifications(token, audience, { unread: filter === "unread" })
      .then((page) => {
        if (cancelled) return;
        setNow(Date.now());
        setLoaded({ key: requestKey, items: page.results, next: page.next_cursor, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Notifications couldn't be loaded.";
        setLoaded({ key: requestKey, items: [], next: null, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [audience, filter, requestKey]);

  // Something else on the page (the header bell) read notifications: start over.
  useEffect(() => {
    const onChanged = () => {
      if (announcing.current) return;
      setReload((n) => n + 1);
    };
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, onChanged);
  }, []);

  // Only the answer to the current request counts; anything else is still loading.
  const current = loaded?.key === requestKey ? loaded : null;
  const loading = current === null;
  const items = current?.items ?? [];
  const hasUnread = items.some((item) => item.read_at === null);

  const announce = () => {
    announcing.current = true;
    notifyNotificationsChanged();
    announcing.current = false;
  };

  const markLocallyRead = (ids: number[] | "all") => {
    const readAt = new Date().toISOString();
    setLoaded((previous) =>
      previous && {
        ...previous,
        items: previous.items.map((item) =>
          item.read_at === null && (ids === "all" || ids.includes(item.id)) ? { ...item, read_at: readAt } : item
        ),
      }
    );
  };

  const loadMore = async () => {
    const token = getAuthToken();
    if (!token || !current?.next) return;
    setLoadingMore(true);
    setActionError(null);
    try {
      const page = await getNotifications(token, audience, { unread: filter === "unread", cursor: current.next });
      setLoaded((previous) =>
        previous && { ...previous, items: [...previous.items, ...page.results], next: page.next_cursor }
      );
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "More notifications couldn't be loaded.");
    } finally {
      setLoadingMore(false);
    }
  };

  const markAllRead = async () => {
    const token = getAuthToken();
    if (!token) return;
    setActionError(null);
    try {
      await markAllNotificationsRead(token, audience);
      markLocallyRead("all");
      announce();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Notifications couldn't be marked as read.");
    }
  };

  const open = async (notification: AppNotification) => {
    const token = getAuthToken();
    if (token && notification.read_at === null) {
      try {
        await markNotificationRead(token, notification.id);
        markLocallyRead([notification.id]);
        announce();
      } catch {
        // Following the link matters more than the dot.
      }
    }
    if (notification.action_url) router.push(notification.action_url);
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Notifications</h1>
          <p className="text-xs text-ink-muted mt-0.5">{INTROS[audience]}</p>
        </div>
        <button
          type="button"
          onClick={markAllRead}
          disabled={loading || !hasUnread}
          className="inline-flex items-center gap-2 bg-surface text-ink border border-line hover:bg-surface-alt font-bold text-xs uppercase tracking-wider px-4 py-2.5 rounded-lg transition-colors cursor-pointer disabled:cursor-default disabled:text-ink-faint disabled:hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            done_all
          </span>
          Mark all read
        </button>
      </div>

      <div role="tablist" aria-label="Show" className="flex gap-2">
        {(
          [
            { value: "all", label: "All" },
            { value: "unread", label: "Unread" },
          ] as const
        ).map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
              filter === option.value
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface text-ink border-line hover:bg-surface-alt"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {actionError && (
        <p role="alert" className="text-sm text-danger font-medium">
          {actionError}
        </p>
      )}

      {current === null ? (
        <div className="flex flex-col items-center justify-center py-20 text-center" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            notifications
          </span>
          <p className="text-sm text-ink-body mt-2">Loading your notifications…</p>
        </div>
      ) : current.error ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center" role="alert">
          <p className="text-sm text-danger font-medium">{current.error}</p>
          <button
            type="button"
            onClick={() => setReload((n) => n + 1)}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-10 text-center">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-faint">
            notifications_none
          </span>
          <p className="text-sm text-ink-body mt-2">
            {filter === "unread" ? "You're all caught up." : "No notifications yet."}
          </p>
        </div>
      ) : (
        <>
          <div className="bg-surface rounded-2xl border border-line overflow-hidden divide-y divide-line-subtle">
            {items.map((item) => (
              <NotificationListItem key={item.id} notification={item} now={now} onOpen={open} />
            ))}
          </div>
          {current.next && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="px-5 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider border border-line bg-surface text-ink hover:bg-surface-alt transition-colors cursor-pointer disabled:cursor-wait disabled:text-ink-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
