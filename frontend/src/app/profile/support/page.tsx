"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import Pagination from "@/components/home/Pagination";
import TicketStatusBadge from "@/components/support/TicketStatusBadge";
import { getMySupportTickets } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { SUPPORT_CATEGORIES, formatRelativeTime } from "@/lib/support";
import type { PaginatedResponse, SupportTicketSummary } from "@/lib/types";

const PAGE_SIZE = 10;

type Tab = "open" | "closed";

const CATEGORY_ICONS = Object.fromEntries(SUPPORT_CATEGORIES.map((c) => [c.value, c.icon]));

/** A loaded page, stored with the request key that produced it. */
interface LoadState {
  key: string;
  data?: PaginatedResponse<SupportTicketSummary>;
  error?: string;
  /** When it arrived; relative times are measured from here, keeping render pure. */
  loadedAt: number;
}

export default function SupportTicketsPage() {
  const [tab, setTab] = useState<Tab>("open");
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<LoadState | null>(null);

  const requestKey = `${tab}:${page}:${reloadToken}`;

  useEffect(() => {
    let cancelled = false;
    const token = getAuthToken();
    (token ? getMySupportTickets(token, { status: tab, page }) : Promise.reject(new Error("Please log in again.")))
      .then((data) => {
        if (!cancelled) setState({ key: requestKey, data, loadedAt: Date.now() });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            key: requestKey,
            error: err instanceof Error ? err.message : "Your tickets couldn't be loaded.",
            loadedAt: Date.now(),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [requestKey, tab, page]);

  const loading = state?.key !== requestKey;
  const data = loading ? undefined : state?.data;
  const error = loading ? undefined : state?.error;
  const totalPages = data ? Math.max(Math.ceil(data.count / PAGE_SIZE), 1) : 1;

  const switchTab = (next: Tab) => {
    setTab(next);
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Support</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            Tell us about a problem and follow our replies here.
          </p>
        </div>
        <Link
          href="/profile/support/new"
          className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-4 py-2.5 rounded-lg shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            add
          </span>
          New ticket
        </Link>
      </div>

      <div role="tablist" aria-label="Ticket status" className="flex gap-2">
        {(
          [
            { value: "open", label: "Open" },
            { value: "closed", label: "Closed" },
          ] as const
        ).map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={tab === option.value}
            onClick={() => switchTab(option.value)}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
              tab === option.value
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface text-ink border-line hover:bg-surface-alt"
            }`}
          >
            {option.label}
            {tab === option.value && data ? ` (${data.count})` : ""}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            support_agent
          </span>
          <p className="text-sm text-ink-body mt-2">Loading your tickets…</p>
        </div>
      ) : error || !data ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center" role="alert">
          <p className="text-sm text-danger font-medium">{error}</p>
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : data.results.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span aria-hidden="true" className="material-symbols-outlined text-[56px] text-ink-muted/40">
            {tab === "open" ? "support_agent" : "inventory"}
          </span>
          <h2 className="text-base font-bold text-ink mt-2">
            {tab === "open" ? "No open tickets" : "No closed tickets yet"}
          </h2>
          <p className="text-sm text-ink-body mt-1 mb-5">
            {tab === "open"
              ? "Having a problem with an order, a payment or your account? Tell us and we'll help."
              : "Tickets you or our team close will be kept here."}
          </p>
          {tab === "open" && (
            <Link
              href="/profile/support/new"
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors"
            >
              Open a ticket
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                arrow_forward
              </span>
            </Link>
          )}
        </div>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {data.results.map((ticket) => (
              <li key={ticket.ticket_number}>
                <TicketCard ticket={ticket} now={state?.loadedAt ?? 0} />
              </li>
            ))}
          </ul>
          {totalPages > 1 && (
            <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
          )}
        </>
      )}
    </div>
  );
}

function TicketCard({ ticket, now }: { ticket: SupportTicketSummary; now: number }) {
  return (
    <Link
      href={`/profile/support/${encodeURIComponent(ticket.ticket_number)}`}
      className={`flex items-start gap-3 sm:gap-4 bg-surface rounded-2xl border p-4 transition-colors hover:bg-surface-alt focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
        ticket.has_unread ? "border-accent/60" : "border-line"
      }`}
    >
      <span
        aria-hidden="true"
        className="w-10 h-10 rounded-xl bg-surface-alt border border-line-subtle flex items-center justify-center shrink-0 text-primary"
      >
        <span className="material-symbols-outlined text-[22px]">
          {CATEGORY_ICONS[ticket.category] ?? "help"}
        </span>
      </span>

      <span className="flex-1 min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-ink break-words">{ticket.subject}</span>
          {ticket.has_unread && (
            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent">
              <span aria-hidden="true" className="w-2 h-2 rounded-full bg-accent" />
              New reply
            </span>
          )}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-muted">
          <span className="font-mono">{ticket.ticket_number}</span>
          <span aria-hidden="true">·</span>
          <span>{ticket.category_label}</span>
          {ticket.order_number && (
            <>
              <span aria-hidden="true">·</span>
              <span>
                Order <span className="font-mono">{ticket.order_number}</span>
              </span>
            </>
          )}
        </span>
      </span>

      <span className="flex flex-col items-end gap-1.5 shrink-0">
        <TicketStatusBadge status={ticket.status} label={ticket.status_label} />
        <time dateTime={ticket.last_activity_at} className="text-[11px] text-ink-muted whitespace-nowrap">
          {formatRelativeTime(ticket.last_activity_at, now)}
        </time>
      </span>
    </Link>
  );
}
