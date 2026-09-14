"use client";

import React from "react";
import Link from "next/link";
import { formatCount, formatTaka } from "@/lib/admin-format";

export type AdminStatTone =
  | "primary"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "accent";

const TONE_CLASSES: Record<AdminStatTone, string> = {
  primary: "bg-primary/10 text-primary",
  info: "bg-blue-500/10 text-blue-600",
  success: "bg-emerald-500/10 text-emerald-600",
  warning: "bg-amber-500/10 text-amber-600",
  danger: "bg-red-500/10 text-red-600",
  accent: "bg-purple-500/10 text-purple-600",
};

export interface AdminStatTrend {
  /** Percentage or absolute delta; sign drives the arrow and colour. */
  value: number;
  /** Context for the delta, e.g. "vs last 30 days". */
  label?: string;
  /** Set true where a rise is bad (e.g. failed payments). */
  invertColors?: boolean;
}

export interface AdminStatCardProps {
  title: string;
  /**
   * Raw value. Numbers are formatted automatically — as ৳ when `currency` is
   * set, otherwise with thousands separators. Strings render verbatim.
   */
  value: string | number | null | undefined;
  /** Formats the value as Bangladeshi Taka (৳). Never $, USD, or BDT. */
  currency?: boolean;
  icon?: string;
  /** Supporting caption under the value. */
  description?: string;
  tone?: AdminStatTone;
  trend?: AdminStatTrend;
  loading?: boolean;
  /** Renders the whole card as a link to a management module. */
  href?: string;
  /** Small pill beside the value, e.g. "Needs Action". */
  badge?: React.ReactNode;
  className?: string;
}

/**
 * KPI tile for the management dashboard.
 *
 * Monetary values always render in ৳ via formatTaka, per the MiniShop currency
 * rule. Visibility of any given card is the caller's decision — the dashboard
 * gates each one on the permission that backs its underlying data.
 */
export default function AdminStatCard({
  title,
  value,
  currency = false,
  icon,
  description,
  tone = "primary",
  trend,
  loading = false,
  href,
  badge,
  className = "",
}: AdminStatCardProps) {
  const displayValue = React.useMemo(() => {
    if (typeof value === "string") return value;
    if (value === null || value === undefined) return currency ? formatTaka(0) : "0";
    return currency ? formatTaka(value) : formatCount(value);
  }, [value, currency]);

  const trendPositive = trend ? trend.value >= 0 : false;
  const trendIsGood = trend?.invertColors ? !trendPositive : trendPositive;

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-ink-muted">
          {title}
        </span>
        {icon && (
          <div
            className={`w-9 h-9 shrink-0 rounded-xl flex items-center justify-center ${TONE_CLASSES[tone]}`}
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
              {icon}
            </span>
          </div>
        )}
      </div>

      <div className="mt-4">
        {loading ? (
          <div
            className="h-8 w-24 bg-surface-alt animate-pulse rounded-md"
            role="status"
            aria-label={`Loading ${title}`}
          />
        ) : (
          <div className="flex items-baseline flex-wrap gap-2">
            <span className="text-2xl font-black text-ink tracking-tight break-all">
              {displayValue}
            </span>
            {badge}
          </div>
        )}

        {!loading && trend && (
          <div
            className={`mt-1.5 inline-flex items-center gap-1 text-[11px] font-bold ${
              trendIsGood ? "text-emerald-600" : "text-red-600"
            }`}
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
              {trendPositive ? "trending_up" : "trending_down"}
            </span>
            <span>
              {trendPositive ? "+" : ""}
              {trend.value}%
            </span>
            {trend.label && (
              <span className="text-ink-muted font-medium">{trend.label}</span>
            )}
          </div>
        )}

        {description && (
          <p className="text-[11px] text-ink-muted mt-1">{description}</p>
        )}
      </div>
    </>
  );

  const baseClass = `bg-surface p-5 rounded-2xl border border-line shadow-xs flex flex-col justify-between ${className}`;

  if (href) {
    return (
      <Link
        href={href}
        className={`${baseClass} transition-colors hover:bg-surface-alt focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
      >
        {body}
      </Link>
    );
  }

  return <div className={baseClass}>{body}</div>;
}
