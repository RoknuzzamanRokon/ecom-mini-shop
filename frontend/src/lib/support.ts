/**
 * Support ticket constants and helpers shared by the customer pages and the
 * management console.
 *
 * The limits mirror backend/support/services.py and validators.py. The backend
 * stays authoritative (it checks each file's real content, which the browser
 * can't); these checks only save a round trip for obvious mistakes.
 */
import type { AuthUser, SupportCategory, SupportPriority, SupportStatus } from "./types";

export const SUPPORT_LIMITS = {
  maxFiles: 5,
  maxFileBytes: 5 * 1024 * 1024,
  subjectMin: 5,
  subjectMax: 150,
  descriptionMin: 10,
  messageMax: 5000,
} as const;

/**
 * Whether to offer this user the customer support pages: they hold
 * `support.view` (CUSTOMER), or everything. A staff account without the
 * CUSTOMER role would only get 403s there, so it isn't shown the links.
 */
export function canUseSupport(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  const permissions = user.permissions ?? [];
  return user.is_superuser || permissions.includes("support.view") || permissions.includes("*");
}

export const SUPPORT_CATEGORIES: {
  value: SupportCategory;
  label: string;
  icon: string;
}[] = [
  { value: "ORDER", label: "Order & delivery", icon: "local_shipping" },
  { value: "PAYMENT", label: "Payment & refund", icon: "payments" },
  { value: "PRODUCT", label: "Wrong or damaged item", icon: "broken_image" },
  { value: "RETURN", label: "Return & exchange", icon: "assignment_return" },
  { value: "ACCOUNT", label: "Account & login", icon: "manage_accounts" },
  { value: "SHOP", label: "Shop or seller complaint", icon: "storefront" },
  { value: "OTHER", label: "Other", icon: "help" },
];

export const SUPPORT_CATEGORY_LABELS: Record<SupportCategory, string> = Object.fromEntries(
  SUPPORT_CATEGORIES.map((c) => [c.value, c.label])
) as Record<SupportCategory, string>;

/** How a customer reads each status (support/serializers.py CUSTOMER_STATUS_LABELS). */
export const CUSTOMER_STATUS_LABELS: Record<SupportStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  WAITING_ON_CUSTOMER: "Waiting on you",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

/** How staff read each status (SupportTicket.STATUS_CHOICES). */
export const STAFF_STATUS_LABELS: Record<SupportStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  WAITING_ON_CUSTOMER: "Waiting on customer",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export const SUPPORT_STATUSES: SupportStatus[] = [
  "OPEN",
  "IN_PROGRESS",
  "WAITING_ON_CUSTOMER",
  "RESOLVED",
  "CLOSED",
];

export const SUPPORT_PRIORITY_LABELS: Record<SupportPriority, string> = {
  LOW: "Low",
  NORMAL: "Normal",
  HIGH: "High",
  URGENT: "Urgent",
};

export const SUPPORT_PRIORITIES: SupportPriority[] = ["LOW", "NORMAL", "HIGH", "URGENT"];

const ALLOWED_TYPES: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "application/pdf": "pdf",
};
const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp", "pdf"]);

/** Value for <input type="file" accept>. */
export const SUPPORT_FILE_ACCEPT =
  "image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf";

export const SUPPORT_FILE_HINT = `JPG, PNG, WebP or PDF · up to ${SUPPORT_LIMITS.maxFiles} files, ${
  SUPPORT_LIMITS.maxFileBytes / (1024 * 1024)
} MB each`;

function looksAllowed(file: File): boolean {
  if (file.type) return file.type in ALLOWED_TYPES;
  // Some browsers leave `type` empty; fall back to the extension.
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ALLOWED_EXTENSIONS.has(extension);
}

/**
 * Adds `incoming` files to `current`, keeping only the ones that pass the
 * type/size/count limits. Returns the new list and, if anything was left
 * out, one message saying why.
 */
export function validateSupportFiles(
  current: File[],
  incoming: File[]
): { files: File[]; error: string | null } {
  const files = [...current];
  const problems: string[] = [];
  for (const file of incoming) {
    if (!looksAllowed(file)) {
      problems.push(`“${file.name}” isn't a JPG, PNG, WebP or PDF file.`);
    } else if (file.size === 0) {
      problems.push(`“${file.name}” is empty.`);
    } else if (file.size > SUPPORT_LIMITS.maxFileBytes) {
      problems.push(`“${file.name}” is larger than 5 MB.`);
    } else if (files.length >= SUPPORT_LIMITS.maxFiles) {
      problems.push(`You can attach up to ${SUPPORT_LIMITS.maxFiles} files.`);
      break;
    } else {
      files.push(file);
    }
  }
  return { files, error: problems.length ? problems.join(" ") : null };
}

export function isImageType(contentType: string): boolean {
  return contentType.startsWith("image/");
}

/** 482113 → "471 KB". */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "24 Sep 2026, 15:04", locale-pinned so server and client render the same text. */
export function formatSupportDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * "just now", "5 min ago", "3 h ago", "2 d ago", then the date. `now` is a
 * parameter (not read here) so components can pass a value held in state and
 * keep render pure.
 */
export function formatRelativeTime(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.floor((now - then) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} d ago`;
  return formatSupportDateTime(iso).split(",")[0];
}

/**
 * Fired on `window` after a ticket page has loaded a ticket (which marks its
 * replies read), so the profile nav can re-count unread tickets without
 * waiting for the next navigation.
 */
export const SUPPORT_UNREAD_EVENT = "minishop:support-unread-changed";

export function notifySupportUnreadChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SUPPORT_UNREAD_EVENT));
}
