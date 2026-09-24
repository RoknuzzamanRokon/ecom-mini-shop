"use client";

/**
 * Support ticket console helpers, colocated with /admin/support like the other
 * governance modules: the permission gates, the list filters and how they are
 * read from the URL, the queue cards, and the page access notice. The backend
 * (support/permissions.py) authorizes every request itself.
 */

import React from "react";
import Link from "next/link";
import type { AdminSelectOption, AdminStatTone } from "@/components/admin/shared";
import type { AdminSupportOrdering, AdminSupportSummary } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  STAFF_STATUS_LABELS,
  SUPPORT_CATEGORIES,
  SUPPORT_PRIORITIES,
  SUPPORT_PRIORITY_LABELS,
  SUPPORT_STATUSES,
} from "@/lib/support";
import type { AuthUser, SupportCategory, SupportPriority, SupportStatus } from "@/lib/types";

/** Mirrors CanViewSupportTickets: the queue, a ticket, the summary, attachments. */
export function canViewSupport(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.supportView);
}

/** Mirrors CanReplySupportTickets: public replies and internal notes. */
export function canReplySupport(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.supportReply);
}

/** Mirrors CanManageSupportTickets: status, priority, category and assignee. */
export function canManageSupport(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.supportManage);
}

/** A status tab: one status, "active" (everything but CLOSED; the default) or "all". */
export type SupportStatusTab = SupportStatus | "active" | "all";

export const SUPPORT_STATUS_TABS: { value: SupportStatusTab; label: string }[] = [
  { value: "active", label: "Active" },
  ...SUPPORT_STATUSES.map((status) => ({ value: status, label: STAFF_STATUS_LABELS[status] })),
  { value: "all", label: "All" },
];

/** Highest first, the order a queue is triaged in. */
export const PRIORITY_OPTIONS: AdminSelectOption[] = [...SUPPORT_PRIORITIES]
  .reverse()
  .map((priority) => ({ value: priority, label: SUPPORT_PRIORITY_LABELS[priority] }));

export const CATEGORY_OPTIONS: AdminSelectOption[] = SUPPORT_CATEGORIES.map((category) => ({
  value: category.value,
  label: category.label,
}));

export const DEFAULT_ORDERING: AdminSupportOrdering = "-last_activity_at";

export const ORDERING_OPTIONS: { value: AdminSupportOrdering; label: string }[] = [
  { value: "-last_activity_at", label: "Latest activity" },
  { value: "last_activity_at", label: "Oldest activity" },
  { value: "-priority", label: "Highest priority" },
  { value: "-created_at", label: "Newest tickets" },
  { value: "created_at", label: "Oldest tickets" },
];

// The page keeps its filters in the URL. The backend answers an unknown value
// with a 400, so anything unrecognised (an old bookmark, a hand-edited link)
// falls back to the default instead of breaking the list.

export function parseStatusTab(raw: string | null): SupportStatusTab {
  if (raw === "all") return "all";
  return (SUPPORT_STATUSES as string[]).includes(raw ?? "") ? (raw as SupportStatus) : "active";
}

export function parsePriority(raw: string | null): SupportPriority | "" {
  return (SUPPORT_PRIORITIES as string[]).includes(raw ?? "") ? (raw as SupportPriority) : "";
}

export function parseCategory(raw: string | null): SupportCategory | "" {
  return SUPPORT_CATEGORIES.some((category) => category.value === raw) ? (raw as SupportCategory) : "";
}

/** "me", "unassigned" or a user id, as the backend accepts. */
export function parseAssigned(raw: string | null): string {
  if (raw === "me" || raw === "unassigned" || /^\d+$/.test(raw ?? "")) return raw as string;
  return "";
}

export function parseOrdering(raw: string | null): AdminSupportOrdering {
  return ORDERING_OPTIONS.find((option) => option.value === raw)?.value ?? DEFAULT_ORDERING;
}

/**
 * The four queue cards. Each opens the list with exactly its own filter (on
 * the default Active tab), so the list shows the number the card promised.
 */
export const QUEUE_VIEWS: {
  key: string;
  title: string;
  icon: string;
  tone: AdminStatTone;
  description: string;
  params: Record<string, string>;
  count: (summary: AdminSupportSummary) => number;
}[] = [
  {
    key: "needs_reply",
    title: "Needs reply",
    icon: "mark_chat_unread",
    tone: "warning",
    description: "The customer wrote last",
    params: { needs_reply: "true" },
    count: (summary) => summary.needs_reply,
  },
  {
    key: "open",
    title: "Open",
    icon: "mark_email_unread",
    tone: "primary",
    description: "New or reopened, not started",
    params: { status: "OPEN" },
    count: (summary) => summary.by_status.OPEN ?? 0,
  },
  {
    key: "unassigned",
    title: "Unassigned",
    icon: "person_off",
    tone: "accent",
    description: "Active tickets nobody owns",
    params: { assigned: "unassigned" },
    count: (summary) => summary.unassigned,
  },
  {
    key: "mine",
    title: "Assigned to me",
    icon: "assignment_ind",
    tone: "info",
    description: "Your active tickets",
    params: { assigned: "me" },
    count: (summary) => summary.assigned_to_me,
  },
];

/**
 * The status buttons on a ticket and their confirm step. Staff can never move
 * a ticket back to OPEN (only a customer reply does), so OPEN has no entry.
 * Every change also adds a public "Status changed to …" line to the thread.
 */
export const STATUS_ACTIONS: Partial<
  Record<SupportStatus, { label: string; icon: string; title: string; message: string; destructive?: boolean }>
> = {
  IN_PROGRESS: {
    label: "Mark in progress",
    icon: "autorenew",
    title: "Move to In progress?",
    message: "Use this when work on the ticket (re)starts.",
  },
  WAITING_ON_CUSTOMER: {
    label: "Wait on customer",
    icon: "hourglass_top",
    title: "Wait on the customer?",
    message:
      "Use this after asking the customer for something. Their next reply moves the ticket back to Open.",
  },
  RESOLVED: {
    label: "Resolve",
    icon: "task_alt",
    title: "Resolve this ticket?",
    message:
      "The customer is told the problem is resolved. If it isn't, their reply reopens the ticket; if it is, they can close it.",
  },
  CLOSED: {
    label: "Close",
    icon: "lock",
    title: "Close this ticket?",
    message:
      "Closing is final: nobody can reply any more, and the customer would have to open a new ticket for further help.",
    destructive: true,
  },
};

// The queue remembers its current view (filters, tab, page) for this browser
// tab, so a ticket's back link returns to it rather than to the bare list.
const LIST_URL_KEY = "minishop:admin-support-list";
export const SUPPORT_LIST_PATH = "/admin/support";

export function rememberSupportListUrl(url: string): void {
  try {
    sessionStorage.setItem(LIST_URL_KEY, url);
  } catch {
    // Storage blocked (private mode, site data off): the link falls back to the list.
  }
}

/** The remembered queue URL, if it is really a queue URL; else the plain list. */
export function readSupportListUrl(): string {
  try {
    const url = sessionStorage.getItem(LIST_URL_KEY);
    if (url === SUPPORT_LIST_PATH || url?.startsWith(`${SUPPORT_LIST_PATH}?`)) return url;
  } catch {
    // As above.
  }
  return SUPPORT_LIST_PATH;
}

/** Shown instead of the module when the operator lacks support.staff.view. */
export function SupportAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-accent/10 text-accent flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">Insufficient Permissions</h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Your account does not hold the permission required to open{" "}
          <strong className="text-ink">Support Tickets</strong>. The ticket queue requires{" "}
          <code className="font-mono text-[11px]">support.staff.view</code>. Contact a Super
          Administrator if you believe this is incorrect.
        </p>
        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}
