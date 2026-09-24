import React from "react";
import type { SupportStatus } from "@/lib/types";
import { CUSTOMER_STATUS_LABELS } from "@/lib/support";

const TONES: Record<SupportStatus, string> = {
  OPEN: "bg-primary/10 text-primary border-primary/25",
  IN_PROGRESS: "bg-accent/10 text-accent border-accent/30",
  // The one status that asks something of the customer, so it stands out.
  WAITING_ON_CUSTOMER: "bg-accent text-on-accent border-accent",
  RESOLVED: "bg-success/10 text-success border-success/30",
  CLOSED: "bg-surface-sunken text-ink-muted border-line",
};

const ICONS: Record<SupportStatus, string> = {
  OPEN: "mark_email_unread",
  IN_PROGRESS: "autorenew",
  WAITING_ON_CUSTOMER: "reply",
  RESOLVED: "task_alt",
  CLOSED: "lock",
};

interface TicketStatusBadgeProps {
  status: SupportStatus;
  /** The API's status_label; falls back to the customer wording. */
  label?: string;
  size?: "sm" | "md";
}

/** A ticket's status as the customer sees it (theme tokens only). */
export default function TicketStatusBadge({ status, label, size = "sm" }: TicketStatusBadgeProps) {
  const text = label || CUSTOMER_STATUS_LABELS[status] || status;
  const sizing =
    size === "md" ? "text-xs px-2.5 py-1 gap-1.5" : "text-[11px] px-2 py-0.5 gap-1";
  return (
    <span
      className={`inline-flex items-center shrink-0 rounded-full border font-bold whitespace-nowrap ${sizing} ${
        TONES[status] ?? TONES.CLOSED
      }`}
    >
      <span aria-hidden="true" className={`material-symbols-outlined ${size === "md" ? "text-[15px]" : "text-[13px]"}`}>
        {ICONS[status] ?? "help"}
      </span>
      {text}
    </span>
  );
}
