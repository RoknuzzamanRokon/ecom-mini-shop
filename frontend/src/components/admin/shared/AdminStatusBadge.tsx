"use client";

import React from "react";
import { humanizeToken } from "@/lib/admin-format";

/**
 * Visual tone of a status pill. Domain-neutral so new statuses can be mapped
 * without adding new styling.
 */
export type AdminStatusTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "accent";

/**
 * ==============================================================================
 * STATUS -> TONE MAP
 * ==============================================================================
 * Every key below is an actual status constant defined in the Django models.
 * No status is invented here.
 *
 *   Product (shop/models.py)   DRAFT SUBMITTED APPROVED REJECTED PUBLISHED UNPUBLISHED
 *   Order   (shop/models.py)   PENDING CONFIRMED PROCESSING SHIPPED DELIVERED CANCELLED
 *   Payment (shop/models.py)   PENDING PROCESSING PAID FAILED CANCELLED REFUNDED
 *                              PARTIALLY_REFUNDED
 *   Refund/Txn (shop/models)   PENDING COMPLETED FAILED
 *   Shop    (shops/models.py)  DRAFT PENDING APPROVED ACTIVE SUSPENDED REJECTED
 *   Seller  (sellers/models)   PENDING UNDER_REVIEW APPROVED ACTIVE SUSPENDED REJECTED
 *
 * Legacy lowercase order statuses ("pending", "shipped", ...) normalize to the
 * same keys because lookup is case-insensitive.
 */
const STATUS_TONES: Record<string, AdminStatusTone> = {
  // Terminal success / healthy operating states
  APPROVED: "success",
  ACTIVE: "success",
  PUBLISHED: "success",
  PAID: "success",
  COMPLETED: "success",
  DELIVERED: "success",

  // In-flight / informational states
  SUBMITTED: "info",
  UNDER_REVIEW: "info",
  CONFIRMED: "info",
  PROCESSING: "info",
  SHIPPED: "info",

  // Awaiting a human decision
  PENDING: "warning",
  PARTIALLY_REFUNDED: "warning",

  // Enforcement / failure states
  REJECTED: "danger",
  SUSPENDED: "danger",
  FAILED: "danger",

  // Inactive but not punitive
  DRAFT: "neutral",
  UNPUBLISHED: "neutral",
  CANCELLED: "neutral",

  // Financial reversal
  REFUNDED: "accent",
};

/**
 * Mid-tone (-600) text on a /10 tint reads with adequate contrast on both the
 * light and dark surfaces of every MiniShop theme. This mirrors the palette the
 * existing admin dashboard already uses. The `dark:` variant is deliberately
 * avoided: this project toggles themes with a `.dark` class on :root, while
 * Tailwind v4's default `dark:` variant tracks prefers-color-scheme, so the two
 * would disagree whenever the user's OS and in-app theme differ.
 */
const TONE_CLASSES: Record<AdminStatusTone, string> = {
  neutral: "bg-surface-alt text-ink-muted border-line",
  info: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  success: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  warning: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  danger: "bg-red-500/10 text-red-600 border-red-500/20",
  accent: "bg-purple-500/10 text-purple-600 border-purple-500/20",
};

const DOT_CLASSES: Record<AdminStatusTone, string> = {
  neutral: "bg-ink-muted",
  info: "bg-blue-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  accent: "bg-purple-500",
};

const SIZE_CLASSES = {
  sm: "text-[10px] px-1.5 py-0.5 gap-1",
  md: "text-[11px] px-2 py-0.5 gap-1.5",
} as const;

/** Resolves the tone for a status token; unknown tokens fall back to neutral. */
export function getStatusTone(status: string | null | undefined): AdminStatusTone {
  if (!status) return "neutral";
  return STATUS_TONES[status.trim().toUpperCase()] ?? "neutral";
}

export interface AdminStatusBadgeProps {
  /** Raw backend status token, e.g. "UNDER_REVIEW". */
  status: string | null | undefined;
  /** Overrides the derived label. */
  label?: string;
  /** Overrides the derived tone. */
  tone?: AdminStatusTone;
  size?: keyof typeof SIZE_CLASSES;
  /** Renders a leading status dot. */
  withDot?: boolean;
  className?: string;
}

/**
 * Reusable status indicator for management tables and detail panes.
 *
 * Unknown or missing statuses render safely as a neutral pill rather than
 * throwing or rendering nothing. The label is always rendered as escaped text
 * through React children — never via dangerouslySetInnerHTML.
 */
export default function AdminStatusBadge({
  status,
  label,
  tone,
  size = "md",
  withDot = true,
  className = "",
}: AdminStatusBadgeProps) {
  const raw = (status ?? "").trim();
  const resolvedTone = tone ?? getStatusTone(raw);
  const resolvedLabel = label ?? (raw ? humanizeToken(raw) : "Unknown");

  return (
    <span
      className={`inline-flex items-center rounded-md border font-bold uppercase tracking-wide whitespace-nowrap ${
        SIZE_CLASSES[size]
      } ${TONE_CLASSES[resolvedTone]} ${className}`}
      title={resolvedLabel}
    >
      {withDot && (
        <span
          aria-hidden="true"
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT_CLASSES[resolvedTone]}`}
        />
      )}
      {resolvedLabel}
    </span>
  );
}
