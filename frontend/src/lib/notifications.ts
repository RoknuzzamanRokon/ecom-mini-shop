/**
 * The notification inbox: types, the /api/notifications/ client and the
 * "something changed" event (docs/NOTIFICATION_SYSTEM.md §8, §9).
 *
 * Every call goes through `customerRequest`, the same authenticated transport
 * as the rest of the app, so an expired access token is refreshed once and
 * retried. The backend decides who may read which inbox; `audience` only says
 * which one to ask for.
 */
import { customerRequest } from "./api";

/** Which surface shows a notification: the storefront, the Seller Center or the Console. */
export type NotificationAudience = "CUSTOMER" | "SELLER" | "STAFF";

export type NotificationPriority = "NORMAL" | "HIGH";

export interface AppNotification {
  id: number;
  event_type: string;
  category: string;
  title: string;
  /** Plain text, possibly several paragraphs. */
  body: string;
  /** An app path, or "" when there is nothing to open. */
  action_url: string;
  priority: NotificationPriority;
  occurred_at: string;
  read_at: string | null;
}

export interface NotificationPage {
  results: AppNotification[];
  /** Pass back as `cursor` for the next page; null on the last one. */
  next_cursor: string | null;
}

export type NotificationChannelKey = "in_app" | "email";

export interface NotificationChannelState {
  enabled: boolean;
  /** A required channel, which can't be switched off. */
  locked: boolean;
}

export interface NotificationPreference {
  category: string;
  label: string;
  /** Only the channels the category uses: no `email` for in-app-only categories. */
  channels: Partial<Record<NotificationChannelKey, NotificationChannelState>>;
}

export interface NotificationPreferenceChange {
  category: string;
  channels: Partial<Record<NotificationChannelKey, { enabled: boolean }>>;
}

/** Where each audience reads its whole inbox. */
export const NOTIFICATION_INBOX_PATHS: Record<NotificationAudience, string> = {
  CUSTOMER: "/profile/notifications",
  SELLER: "/seller/notifications",
  STAFF: "/admin/notifications",
};

/** Material Symbols per category (backend/notifications/categories.py). */
const CATEGORY_ICONS: Record<string, string> = {
  ORDERS: "local_shipping",
  SELLER_ORDERS: "shopping_bag",
  PAYMENTS: "payments",
  SUPPORT: "support_agent",
  ACCOUNT: "badge",
  SHOPS: "storefront",
  CATALOG: "inventory_2",
  INVENTORY: "warehouse",
  REVIEWS: "reviews",
  WALLET: "toll",
  STAFF_QUEUE: "assignment",
};

export function notificationIcon(category: string): string {
  return CATEGORY_ICONS[category] ?? "notifications";
}

/** "99+" past 99, as the bell's badge shows it. */
export function formatUnreadBadge(count: number): string {
  return count > 99 ? "99+" : String(count);
}

/**
 * Fired on `window` whenever notifications were read, so every bell and inbox
 * on the page re-counts at once instead of waiting for the next poll.
 */
export const NOTIFICATIONS_CHANGED_EVENT = "minishop:notifications-changed";

export function notifyNotificationsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
}

// --- API -------------------------------------------------------------------

const BASE = "/api/notifications/";
const OFFLINE_MESSAGE = "Couldn't reach MiniShop. Check your connection and try again.";

async function request(endpoint: string, token: string, options: RequestInit = {}): Promise<Response> {
  try {
    return await customerRequest(endpoint, token, { cache: "no-store", ...options });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
}

/** The backend's own words (`detail`, else the first field error), else `fallback`. */
async function responseError(res: Response, fallback: string): Promise<Error> {
  const data = await res.json().catch(() => ({}));
  if (typeof data?.detail === "string") return new Error(data.detail);
  for (const value of Object.values(data ?? {})) {
    if (Array.isArray(value) && typeof value[0] === "string") return new Error(value[0]);
  }
  return new Error(fallback);
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export async function getNotifications(
  token: string,
  audience: NotificationAudience,
  options: { unread?: boolean; cursor?: string | null } = {}
): Promise<NotificationPage> {
  const res = await request(
    `${BASE}${query({ audience, unread: options.unread ? "1" : undefined, cursor: options.cursor ?? undefined })}`,
    token
  );
  if (!res.ok) throw await responseError(res, "Notifications couldn't be loaded.");
  return (await res.json()) as NotificationPage;
}

export async function getUnreadNotificationCount(
  token: string,
  audience: NotificationAudience
): Promise<number> {
  const res = await request(`${BASE}unread-count/${query({ audience })}`, token);
  if (!res.ok) throw await responseError(res, "Unread notifications couldn't be counted.");
  const data = await res.json();
  return typeof data?.unread === "number" ? data.unread : 0;
}

export async function markNotificationRead(token: string, id: number): Promise<void> {
  const res = await request(`${BASE}${id}/read/`, token, { method: "POST" });
  if (!res.ok) throw await responseError(res, "The notification couldn't be marked as read.");
}

/** Marks every unread notification in that inbox read; returns how many changed. */
export async function markAllNotificationsRead(
  token: string,
  audience: NotificationAudience
): Promise<number> {
  const res = await request(`${BASE}read-all/${query({ audience })}`, token, { method: "POST" });
  if (!res.ok) throw await responseError(res, "Notifications couldn't be marked as read.");
  const data = await res.json();
  return typeof data?.updated === "number" ? data.updated : 0;
}

export async function getNotificationPreferences(
  token: string,
  audience?: NotificationAudience
): Promise<NotificationPreference[]> {
  const res = await request(`${BASE}preferences/${query({ audience })}`, token);
  if (!res.ok) throw await responseError(res, "Notification settings couldn't be loaded.");
  return (await res.json()) as NotificationPreference[];
}

/** Saves some toggles and returns the settings as they now stand. */
export async function updateNotificationPreferences(
  token: string,
  changes: NotificationPreferenceChange[],
  audience?: NotificationAudience
): Promise<NotificationPreference[]> {
  const res = await request(`${BASE}preferences/${query({ audience })}`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw await responseError(res, "Notification settings couldn't be saved.");
  return (await res.json()) as NotificationPreference[];
}
