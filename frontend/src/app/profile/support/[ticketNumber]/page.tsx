"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AdminConfirmModal from "@/components/admin/shared/AdminConfirmModal";
import AttachmentPicker from "@/components/support/AttachmentPicker";
import type { AttachmentLoader } from "@/components/support/SecureAttachment";
import TicketStatusBadge from "@/components/support/TicketStatusBadge";
import TicketThread from "@/components/support/TicketThread";
import {
  closeSupportTicket,
  fetchSupportAttachment,
  getMySupportTicket,
  replyToSupportTicket,
} from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import {
  SUPPORT_CATEGORIES,
  SUPPORT_LIMITS,
  formatSupportDateTime,
  notifySupportUnreadChanged,
} from "@/lib/support";
import type { SupportStatus, SupportTicket } from "@/lib/types";

/** D12: no push, so the ticket is re-read on this timer while the tab is visible, and on focus. */
const REFRESH_INTERVAL_MS = 60_000;
/** Coming back to the tab fires both focus and visibilitychange; one request is enough. */
const MIN_REFRESH_GAP_MS = 5_000;

const CATEGORY_ICONS = Object.fromEntries(SUPPORT_CATEGORIES.map((c) => [c.value, c.icon]));

/** A customer reply on these statuses reopens the ticket (SupportTicket.CUSTOMER_REOPEN_STATUSES). */
const REOPEN_ON_REPLY: SupportStatus[] = ["WAITING_ON_CUSTOMER", "RESOLVED"];

function requireToken(): string {
  const token = getAuthToken();
  if (!token) throw new Error("Please log in again.");
  return token;
}

/** Stable (module level), as SecureAttachment needs; reads the token on every call. */
const loadAttachment: AttachmentLoader = (url) =>
  Promise.resolve().then(() => fetchSupportAttachment(url, requireToken()));

/** What the page holds for the ticket in the URL. */
interface LoadState {
  /** The URL's ticket number (the key), which may differ in case from the ticket's own. */
  ticketNumber: string;
  /** null: no such ticket, or not yours (the API answers both with 404). */
  ticket: SupportTicket | null;
  /** Only when nothing has loaded yet; a failed background refresh keeps the last good copy. */
  error?: string;
}

export default function SupportTicketPage() {
  const params = useParams<{ ticketNumber: string }>();
  const ticketNumber = params?.ticketNumber ?? "";

  const [state, setState] = useState<LoadState | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [announcement, setAnnouncement] = useState("");

  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  const [confirmingClose, setConfirmingClose] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);

  // Bumped by every read and every successful write, so an older read that
  // answers late can't overwrite newer data.
  const generation = useRef(0);
  const lastReadAt = useRef(0);
  const shownTicket = useRef<SupportTicket | null>(null);

  const current = state?.ticketNumber === ticketNumber ? state : null;
  const ticket = current?.ticket ?? null;

  useEffect(() => {
    shownTicket.current = ticket;
  }, [ticket]);

  useEffect(() => {
    if (!ticketNumber) return;
    const mine = ++generation.current;
    lastReadAt.current = Date.now();
    Promise.resolve()
      .then(() => getMySupportTicket(ticketNumber, requireToken()))
      .then((loaded) => {
        if (mine !== generation.current) return;
        const before = shownTicket.current;
        if (before && loaded && before.ticket_number === loaded.ticket_number) {
          const lastSeenId = before.messages.length ? before.messages[before.messages.length - 1].id : 0;
          const fresh = loaded.messages.filter((m) => m.id > lastSeenId && m.author_type === "STAFF").length;
          if (fresh > 0) {
            setAnnouncement(fresh === 1 ? "New reply from MiniShop Support." : `${fresh} new replies from MiniShop Support.`);
          }
        }
        setState({ ticketNumber, ticket: loaded });
        // Opening the ticket marked its replies read; let the nav badge catch up.
        notifySupportUnreadChanged();
      })
      .catch((err: unknown) => {
        if (mine !== generation.current) return;
        setState((prev) =>
          prev?.ticketNumber === ticketNumber && prev.ticket
            ? prev
            : {
                ticketNumber,
                ticket: null,
                error: err instanceof Error ? err.message : "This ticket couldn't be loaded.",
              }
        );
      });
  }, [ticketNumber, refreshKey]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastReadAt.current < MIN_REFRESH_GAP_MS) return;
      setRefreshKey((k) => k + 1);
    };
    const timer = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

  /** Every write answers with the whole ticket: show it, and drop any read still in flight. */
  const applyTicket = useCallback(
    (updated: SupportTicket) => {
      generation.current += 1;
      setState({ ticketNumber, ticket: updated });
    },
    [ticketNumber]
  );

  const sendReply = async (event: React.FormEvent) => {
    event.preventDefault();
    if (sending || !ticket) return;
    const body = draft.trim();
    if (!body && files.length === 0) {
      setReplyError("Write a message or attach a file.");
      return;
    }
    setReplyError(null);
    setSending(true);
    try {
      const updated = await replyToSupportTicket(ticketNumber, body, files, requireToken());
      applyTicket(updated);
      setDraft("");
      setFiles([]);
      setAnnouncement(
        REOPEN_ON_REPLY.includes(ticket.status) && updated.status === "OPEN"
          ? "Reply sent. The ticket is open again."
          : "Reply sent."
      );
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : "Your reply couldn't be sent. Please try again.");
      // The ticket may have changed under us (closed by the team, say).
      setRefreshKey((k) => k + 1);
    } finally {
      setSending(false);
    }
  };

  const openCloseDialog = () => {
    setCloseError(null);
    setConfirmingClose(true);
  };

  const closeTicket = async () => {
    setCloseError(null);
    try {
      const updated = await closeSupportTicket(ticketNumber, requireToken());
      applyTicket(updated);
      setConfirmingClose(false);
      setAnnouncement("Ticket closed.");
    } catch (err) {
      setCloseError(err instanceof Error ? err.message : "The ticket couldn't be closed. Please try again.");
      setRefreshKey((k) => k + 1);
    }
  };

  const retry = () => {
    setState(null);
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="flex flex-col gap-5">
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <Link
        href="/profile/support"
        className="self-start inline-flex items-center gap-1 text-xs font-semibold text-ink-muted hover:text-primary transition-colors"
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
          arrow_back
        </span>
        All tickets
      </Link>

      {!current ? (
        <div className="flex flex-col items-center justify-center py-20 text-center" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            support_agent
          </span>
          <p className="text-sm text-ink-body mt-2">Loading your ticket…</p>
        </div>
      ) : current.error ? (
        <div className="bg-surface rounded-2xl border border-line p-8 text-center" role="alert">
          <p className="text-sm text-danger font-medium">{current.error}</p>
          <button
            type="button"
            onClick={retry}
            className="mt-3 text-xs font-bold uppercase tracking-wider text-primary hover:underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : !ticket ? (
        <TicketNotFound />
      ) : (
        <>
          <TicketHeader ticket={ticket} onClose={openCloseDialog} />
          <StatusNote ticket={ticket} onClose={openCloseDialog} />

          <div className="bg-surface rounded-2xl border border-line shadow-sm p-4 sm:p-5">
            <TicketThread messages={ticket.messages} viewer="customer" loadAttachment={loadAttachment} />
          </div>

          {ticket.can_reply ? (
            <ReplyBox
              draft={draft}
              onDraftChange={setDraft}
              files={files}
              onFilesChange={setFiles}
              sending={sending}
              error={replyError}
              onSubmit={sendReply}
            />
          ) : (
            <ClosedNote ticket={ticket} />
          )}

          <AdminConfirmModal
            open={confirmingClose && ticket.can_close}
            title="Close this ticket?"
            icon="lock"
            confirmLabel="Close ticket"
            cancelLabel="Keep it open"
            onCancel={() => setConfirmingClose(false)}
            onConfirm={closeTicket}
            message={
              <>
                <p>
                  Close it if your problem is solved. You won&apos;t be able to reply afterwards; if you
                  need help again, you can open a new ticket.
                </p>
                {(draft.trim() || files.length > 0) && (
                  <p className="mt-2 font-semibold text-ink-body">Your unsent reply will be discarded.</p>
                )}
                {closeError && (
                  <p role="alert" className="mt-2 font-semibold text-danger">
                    {closeError}
                  </p>
                )}
              </>
            }
          />
        </>
      )}
    </div>
  );
}

function TicketHeader({ ticket, onClose }: { ticket: SupportTicket; onClose: () => void }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <TicketStatusBadge status={ticket.status} label={ticket.status_label} size="md" />
          <span className="text-xs text-ink-muted font-mono">{ticket.ticket_number}</span>
        </div>
        <h1 className="text-xl font-bold text-ink mt-2 break-words">{ticket.subject}</h1>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="material-symbols-outlined text-[16px] text-primary">
              {CATEGORY_ICONS[ticket.category] ?? "help"}
            </span>
            {ticket.category_label}
          </span>
          {ticket.order_number && (
            <>
              <span aria-hidden="true">·</span>
              <Link
                href={`/profile/orders/${encodeURIComponent(ticket.order_number)}`}
                className="font-semibold text-primary hover:underline"
              >
                Order <span className="font-mono">{ticket.order_number}</span>
              </Link>
            </>
          )}
          <span aria-hidden="true">·</span>
          <span>
            Opened <time dateTime={ticket.created_at}>{formatSupportDateTime(ticket.created_at)}</time>
          </span>
        </p>
      </div>

      {ticket.can_close && (
        <button
          type="button"
          onClick={onClose}
          className="self-start inline-flex items-center gap-1.5 shrink-0 px-4 py-2.5 rounded-lg border border-line bg-surface hover:bg-surface-alt text-ink font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            lock
          </span>
          Close ticket
        </button>
      )}
    </div>
  );
}

/** A line under the header for the two statuses that ask something of the customer. */
function StatusNote({ ticket, onClose }: { ticket: SupportTicket; onClose: () => void }) {
  if (ticket.status === "RESOLVED") {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 rounded-2xl border border-success/30 bg-success/10">
        <span aria-hidden="true" className="material-symbols-outlined text-[24px] text-success shrink-0">
          task_alt
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-ink">We&apos;ve marked this as resolved</p>
          <p className="text-xs text-ink-body mt-0.5">
            Still having the problem? Reply below and the ticket opens again. If everything is fine, you can
            close it.
          </p>
        </div>
        {ticket.can_close && (
          <button
            type="button"
            onClick={onClose}
            className="self-start sm:self-auto shrink-0 px-4 py-2 rounded-lg bg-success/15 hover:bg-success/25 text-success font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            All sorted, close it
          </button>
        )}
      </div>
    );
  }
  if (ticket.status === "WAITING_ON_CUSTOMER") {
    return (
      <div className="flex items-start gap-3 p-4 rounded-2xl border border-accent/40 bg-accent/10">
        <span aria-hidden="true" className="material-symbols-outlined text-[24px] text-accent shrink-0">
          reply
        </span>
        <div className="min-w-0">
          <p className="text-sm font-bold text-ink">We&apos;re waiting for your reply</p>
          <p className="text-xs text-ink-body mt-0.5">
            Our team needs a little more from you. Reply below so we can carry on.
          </p>
        </div>
      </div>
    );
  }
  return null;
}

interface ReplyBoxProps {
  draft: string;
  onDraftChange: (value: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  sending: boolean;
  error: string | null;
  onSubmit: (event: React.FormEvent) => void;
}

function ReplyBox({ draft, onDraftChange, files, onFilesChange, sending, error, onSubmit }: ReplyBoxProps) {
  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="bg-surface rounded-2xl border border-line shadow-sm p-4 sm:p-5 flex flex-col gap-3"
    >
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor="support-reply" className="text-sm font-bold text-ink">
          Your reply
        </label>
        <span className="text-[11px] text-ink-faint" aria-hidden="true">
          {draft.length}/{SUPPORT_LIMITS.messageMax}
        </span>
      </div>

      {error && (
        <div
          id="support-reply-error"
          role="alert"
          className="flex items-start gap-2 p-3 rounded-lg border border-danger/40 bg-danger/10 text-sm text-danger"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0">
            error
          </span>
          <p>{error}</p>
        </div>
      )}

      <textarea
        id="support-reply"
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            e.currentTarget.form?.requestSubmit();
          }
        }}
        maxLength={SUPPORT_LIMITS.messageMax}
        rows={4}
        disabled={sending}
        placeholder="Write your message…"
        aria-invalid={Boolean(error)}
        aria-describedby={`support-reply-hint${error ? " support-reply-error" : ""}`}
        className={`w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint resize-y min-h-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-60 ${
          error ? "border-danger" : "border-line"
        }`}
      />
      <p id="support-reply-hint" className="-mt-1.5 text-[11px] text-ink-faint">
        Please don&apos;t include passwords or full card numbers. Ctrl + Enter sends.
      </p>

      <AttachmentPicker files={files} onChange={onFilesChange} disabled={sending} />

      <div className="flex justify-end pt-2 border-t border-line-subtle">
        <button
          type="submit"
          disabled={sending}
          className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span aria-hidden="true" className={`material-symbols-outlined text-[18px] ${sending ? "animate-spin" : ""}`}>
            {sending ? "progress_activity" : "send"}
          </span>
          {sending ? "Sending…" : "Send reply"}
        </button>
      </div>
    </form>
  );
}

function ClosedNote({ ticket }: { ticket: SupportTicket }) {
  const newTicketHref = ticket.order_number
    ? `/profile/support/new?order=${encodeURIComponent(ticket.order_number)}`
    : "/profile/support/new";
  return (
    <div className="bg-surface rounded-2xl border border-line p-6 text-center">
      <span aria-hidden="true" className="material-symbols-outlined text-[36px] text-ink-muted/60">
        lock
      </span>
      <h2 className="text-base font-bold text-ink mt-1">This ticket is closed</h2>
      <p className="text-sm text-ink-body mt-1 mb-5">
        {ticket.closed_at ? (
          <>
            Closed <time dateTime={ticket.closed_at}>{formatSupportDateTime(ticket.closed_at)}</time>.{" "}
          </>
        ) : null}
        Closed tickets can&apos;t be replied to. If you still need help, open a new ticket.
      </p>
      <Link
        href={newTicketHref}
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
          add
        </span>
        Open a new ticket
      </Link>
    </div>
  );
}

function TicketNotFound() {
  return (
    <div className="bg-surface rounded-2xl border border-line p-10 text-center max-w-lg mx-auto w-full">
      <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-surface-alt flex items-center justify-center text-ink-muted">
        <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
          search_off
        </span>
      </div>
      <h1 className="text-lg font-bold text-ink">Ticket not found</h1>
      <p className="text-sm text-ink-muted mt-1 mb-6 leading-relaxed">
        We couldn&apos;t find this ticket in your account. Check the link, or pick it from your list.
      </p>
      <Link
        href="/profile/support"
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
          arrow_back
        </span>
        Back to my tickets
      </Link>
    </div>
  );
}
