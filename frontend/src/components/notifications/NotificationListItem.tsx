"use client";

import clsx from "clsx";

import { formatRelativeTime } from "@/lib/support";
import { notificationIcon, type AppNotification } from "@/lib/notifications";

/**
 * One notification as a button: category icon (accent-tinted when HIGH
 * priority, i.e. it needs acting on), title, body, relative time and an
 * unread dot. Shared by the bell's dropdown (one-line body) and the inbox
 * pages (full body). `now` comes from the caller so rendering stays pure.
 */
export default function NotificationListItem({
  notification,
  now,
  onOpen,
  compact = false,
  className,
}: {
  notification: AppNotification;
  now: number;
  onOpen: (notification: AppNotification) => void;
  compact?: boolean;
  className?: string;
}) {
  const unread = notification.read_at === null;
  const high = notification.priority === "HIGH";

  return (
    <button
      type="button"
      onClick={() => onOpen(notification)}
      data-notification-item
      className={clsx(
        "group w-full flex items-start gap-3 text-left px-4 py-3 transition-colors",
        "hover:bg-surface-alt focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
        unread ? "bg-primary/5" : "bg-transparent",
        className
      )}
    >
      <span
        aria-hidden="true"
        className={clsx(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          high ? "bg-accent/15 text-accent" : "bg-primary/10 text-primary"
        )}
      >
        <span className="material-symbols-outlined text-[18px]">{notificationIcon(notification.category)}</span>
      </span>

      <span className="min-w-0 flex-1">
        <span className={clsx("block text-sm leading-snug text-ink", unread ? "font-semibold" : "font-medium")}>
          {notification.title}
        </span>
        <span
          className={clsx(
            "mt-0.5 text-xs leading-relaxed text-ink-muted",
            // line-clamp sets its own display, so `block` only goes on the full body.
            compact ? "line-clamp-1" : "block whitespace-pre-line"
          )}
        >
          {notification.body}
        </span>
        <span className="mt-1 block text-[11px] text-ink-faint">
          <time dateTime={notification.occurred_at}>{formatRelativeTime(notification.occurred_at, now)}</time>
        </span>
      </span>

      {unread ? (
        <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent">
          <span className="sr-only">Unread</span>
        </span>
      ) : (
        <span aria-hidden="true" className="mt-2 h-2 w-2 shrink-0" />
      )}
    </button>
  );
}
