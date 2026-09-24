"use client";

import React, { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminSupportAssignee,
  AdminSupportCustomerDetail,
  AdminSupportMessageInput,
  AdminSupportTicketDetail,
  AdminSupportTicketUpdate,
  assignAdminSupportTicket,
  fetchAdminSupportAttachment,
  getAdminSupportAssignees,
  getAdminSupportTicket,
  postAdminSupportMessage,
  updateAdminSupportTicket,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  STAFF_STATUS_LABELS,
  SUPPORT_CATEGORIES,
  SUPPORT_LIMITS,
  SUPPORT_PRIORITIES,
  SUPPORT_PRIORITY_LABELS,
} from "@/lib/support";
import type { SupportCategory, SupportPriority, SupportStatus } from "@/lib/types";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import AttachmentPicker from "@/components/support/AttachmentPicker";
import type { AttachmentLoader } from "@/components/support/SecureAttachment";
import TicketThread from "@/components/support/TicketThread";
import {
  STATUS_ACTIONS,
  SUPPORT_LIST_PATH,
  SupportAccessNotice,
  canManageSupport,
  canReplySupport,
  canViewSupport,
  readSupportListUrl,
} from "../supportGovernance";

/** D12: no push, so the ticket is re-read on this timer while the tab is visible, and on focus. */
const REFRESH_INTERVAL_MS = 60_000;
/** Coming back to the tab fires both focus and visibilitychange; one request is enough. */
const MIN_REFRESH_GAP_MS = 5_000;

const NO_SESSION = "No active session token was found. Please sign in again.";

const CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg px-2.5 py-2 text-xs text-ink transition-colors cursor-pointer focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-60 disabled:cursor-wait";

function requireToken(): string {
  const token = getAuthToken();
  if (!token) throw new AdminApiError(NO_SESSION, 401);
  return token;
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/** Stable (module level), as SecureAttachment needs; reads the token on every call. */
const loadAttachment: AttachmentLoader = (url) =>
  Promise.resolve().then(() => fetchAdminSupportAttachment(requireToken(), url));

/** The back link's target is read from sessionStorage, which the server can't see. */
const subscribeToNothing = () => () => {};
const serverListUrl = () => SUPPORT_LIST_PATH;

/** What the page holds for the ticket in the URL. */
interface LoadState {
  /** The URL's ticket number (the key), which may differ in case from the ticket's own. */
  ticketNumber: string;
  ticket: AdminSupportTicketDetail | null;
  notFound?: boolean;
  /** Only when nothing has loaded yet; a failed background refresh keeps the last good copy. */
  error?: string;
}

export default function AdminSupportTicketPage() {
  const params = useParams<{ ticketNumber: string }>();
  const ticketNumber = params?.ticketNumber ?? "";
  const { user } = useAuth();

  const canView = canViewSupport(user);
  const canReply = canReplySupport(user);
  const canManage = canManageSupport(user);
  const canOpenCustomer = hasAnyPermission(user, ADMIN_PERMISSIONS.customersView);
  const canOpenOrder = hasAnyPermission(user, ADMIN_PERMISSIONS.ordersView);
  const backHref = useSyncExternalStore(subscribeToNothing, readSupportListUrl, serverListUrl);

  const [state, setState] = useState<LoadState | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [announcement, setAnnouncement] = useState("");

  // Bumped by every read and every successful write, so an older read that
  // answers late can't overwrite newer data.
  const generation = useRef(0);
  const lastReadAt = useRef(0);
  const shownTicket = useRef<AdminSupportTicketDetail | null>(null);

  const current = state?.ticketNumber === ticketNumber ? state : null;
  const ticket = current?.ticket ?? null;

  useEffect(() => {
    shownTicket.current = ticket;
  }, [ticket]);

  useEffect(() => {
    if (!canView || !ticketNumber) return;
    const mine = ++generation.current;
    lastReadAt.current = Date.now();
    Promise.resolve()
      .then(() => getAdminSupportTicket(requireToken(), ticketNumber))
      .then((loaded) => {
        if (mine !== generation.current) return;
        const before = shownTicket.current;
        if (before && before.ticket_number === loaded.ticket_number) {
          const lastSeenId = before.messages.length ? before.messages[before.messages.length - 1].id : 0;
          const fresh = loaded.messages.filter((m) => m.id > lastSeenId && m.author_type === "CUSTOMER").length;
          if (fresh > 0) {
            setAnnouncement(fresh === 1 ? "New message from the customer." : `${fresh} new messages from the customer.`);
          }
        }
        setState({ ticketNumber, ticket: loaded });
      })
      .catch((err: unknown) => {
        if (mine !== generation.current) return;
        if (err instanceof AdminApiError && err.isNotFound) {
          setState({ ticketNumber, ticket: null, notFound: true });
          return;
        }
        setState((prev) =>
          prev?.ticketNumber === ticketNumber && prev.ticket
            ? prev
            : { ticketNumber, ticket: null, error: messageOf(err, "This ticket couldn't be loaded.") }
        );
      });
  }, [canView, ticketNumber, refreshKey]);

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

  // Everyone the ticket can be assigned to; only managers get the picker.
  const [assignees, setAssignees] = useState<AdminSupportAssignee[]>([]);
  useEffect(() => {
    if (!canManage) return;
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    getAdminSupportAssignees(token)
      .then((rows) => {
        if (!cancelled) setAssignees(rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [canManage]);

  /**
   * Every write answers with the whole ticket: show it, and drop any read still
   * in flight. On failure, re-read (a colleague may have changed the ticket)
   * and rethrow so the control that asked can show the backend's message.
   */
  const runUpdate = useCallback(
    async (request: (token: string) => Promise<AdminSupportTicketDetail>, done: string) => {
      try {
        const updated = await request(requireToken());
        generation.current += 1;
        setState({ ticketNumber, ticket: updated });
        setAnnouncement(done);
      } catch (err) {
        setRefreshKey((k) => k + 1);
        throw err;
      }
    },
    [ticketNumber]
  );

  const sendMessage = useCallback(
    (input: AdminSupportMessageInput) =>
      runUpdate(
        (token) => postAdminSupportMessage(token, ticketNumber, input),
        input.isInternal
          ? "Internal note added."
          : input.setStatus
            ? `Reply sent. Status changed to ${STAFF_STATUS_LABELS[input.setStatus]}.`
            : "Reply sent."
      ),
    [runUpdate, ticketNumber]
  );

  const updateDetails = useCallback(
    (update: AdminSupportTicketUpdate, done: string) =>
      runUpdate((token) => updateAdminSupportTicket(token, ticketNumber, update), done),
    [runUpdate, ticketNumber]
  );

  const assign = useCallback(
    (assigneeId: number | null, done: string) =>
      runUpdate((token) => assignAdminSupportTicket(token, ticketNumber, assigneeId), done),
    [runUpdate, ticketNumber]
  );

  // Status changes go through a confirm step with an optional, staff-only reason.
  const [pendingStatus, setPendingStatus] = useState<SupportStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const requestStatus = (status: SupportStatus) => {
    setStatusError(null);
    setPendingStatus(status);
  };
  const confirmStatus = async (reason: string) => {
    if (!pendingStatus) return;
    setStatusError(null);
    try {
      await updateDetails(
        { status: pendingStatus, ...(reason ? { reason } : {}) },
        `Status changed to ${STAFF_STATUS_LABELS[pendingStatus]}.`
      );
      setPendingStatus(null);
    } catch (err) {
      setStatusError(messageOf(err, "The status couldn't be changed."));
    }
  };

  const retry = () => {
    setState(null);
    setRefreshKey((k) => k + 1);
  };

  if (!canView) {
    return <SupportAccessNotice />;
  }

  const statusCopy = pendingStatus ? STATUS_ACTIONS[pendingStatus] : undefined;

  return (
    <div className="space-y-6">
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <Link
        href={backHref}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
          arrow_back
        </span>
        Back to the queue
      </Link>

      {!current ? (
        <DetailSkeleton />
      ) : current.notFound ? (
        <MessageCard
          icon="search_off"
          title="Ticket not found"
          message="No ticket has this number. Check the link, or find the ticket from the queue."
        />
      ) : current.error || !ticket ? (
        <MessageCard
          icon="error"
          title="Unable to load the ticket"
          message={current.error ?? "An unexpected error occurred."}
          action={
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          }
        />
      ) : (
        <>
          <TicketHeader ticket={ticket} />

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-8 space-y-6 min-w-0">
              <section
                aria-labelledby="support-thread-heading"
                className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6"
              >
                <h2
                  id="support-thread-heading"
                  className="text-sm font-extrabold text-ink uppercase tracking-wider mb-4"
                >
                  Conversation
                </h2>
                <TicketThread messages={ticket.messages} viewer="staff" loadAttachment={loadAttachment} />
              </section>

              {canReply ? (
                <StaffComposer
                  key={ticket.ticket_number}
                  ticket={ticket}
                  canManage={canManage}
                  onSend={sendMessage}
                />
              ) : (
                <p className="text-xs text-ink-muted bg-surface rounded-2xl border border-line p-4">
                  You can read this ticket but not reply to it: replies and internal notes need{" "}
                  <code className="font-mono text-[11px]">support.staff.reply</code>.
                </p>
              )}
            </div>

            <div className="lg:col-span-4 space-y-4">
              {!canManage && (
                <p className="text-[11px] text-ink-muted bg-surface-alt rounded-xl border border-line px-3 py-2">
                  Status, priority, category and assignee can only be changed with{" "}
                  <code className="font-mono">support.staff.manage</code>.
                </p>
              )}
              <StatusCard ticket={ticket} canManage={canManage} onRequest={requestStatus} />
              <DetailsCard ticket={ticket} canManage={canManage} onUpdate={updateDetails} />
              <AssigneeCard
                ticket={ticket}
                canManage={canManage}
                assignees={assignees}
                viewerId={user?.id ?? null}
                viewerAssignable={canReply}
                onAssign={assign}
              />
              <CustomerCard customer={ticket.customer} canOpenProfile={canOpenCustomer} />
              <OrderCard order={ticket.order} canOpenOrder={canOpenOrder} />
              <TimelineCard ticket={ticket} />
            </div>
          </div>

          <AdminConfirmModal
            open={Boolean(pendingStatus && ticket.allowed_transitions.includes(pendingStatus))}
            title={statusCopy?.title ?? ""}
            icon={statusCopy?.icon}
            destructive={statusCopy?.destructive ?? false}
            confirmLabel={statusCopy?.label ?? "Confirm"}
            message={
              <>
                <p>{statusCopy?.message}</p>
                <p className="mt-2">
                  The customer sees “Status changed to{" "}
                  {pendingStatus ? STAFF_STATUS_LABELS[pendingStatus] : ""}” in their conversation.
                </p>
                {statusError && (
                  <p role="alert" className="mt-2 font-semibold text-danger">
                    {statusError}
                  </p>
                )}
              </>
            }
            requireReason
            reasonLabel="Reason (optional, staff only)"
            reasonPlaceholder="Why? It is kept as an internal note and in the audit log, never shown to the customer."
            onConfirm={confirmStatus}
            onCancel={() => setPendingStatus(null)}
          />
        </>
      )}
    </div>
  );
}

// =============================================================================
// PIECES
// =============================================================================

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading ticket">
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-4 w-48 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-6 w-2/3 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 bg-surface-alt animate-pulse rounded-xl" />
          ))}
        </div>
        <div className="lg:col-span-4 space-y-4">
          {[0, 1].map((i) => (
            <div key={i} className="h-28 bg-surface rounded-2xl border border-line shadow-xs animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageCard({
  icon,
  title,
  message,
  action,
}: {
  icon: string;
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
      <div className="w-12 h-12 rounded-2xl bg-surface-alt text-ink-muted flex items-center justify-center">
        <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
          {icon}
        </span>
      </div>
      <div>
        <h1 className="text-sm font-bold text-ink">{title}</h1>
        <p className="text-xs text-ink-muted mt-1 max-w-md">{message}</p>
      </div>
      {action}
    </div>
  );
}

function NeedsReplyMarker() {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent">
      <span aria-hidden="true" className="w-2 h-2 rounded-full bg-accent" />
      Needs reply
    </span>
  );
}

function TicketHeader({ ticket }: { ticket: AdminSupportTicketDetail }) {
  return (
    <div className="bg-surface rounded-2xl border border-line shadow-xs p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <AdminStatusBadge status={ticket.status} label={ticket.status_label} />
        <AdminStatusBadge status={ticket.priority} label={`${ticket.priority_label} priority`} size="sm" />
        {ticket.needs_reply && <NeedsReplyMarker />}
        <span className="font-mono text-[11px] text-ink-muted">{ticket.ticket_number}</span>
      </div>
      <h1 className="mt-2 text-xl font-black text-ink tracking-tight break-words">{ticket.subject}</h1>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
        <span>{ticket.category_label}</span>
        <span aria-hidden="true">·</span>
        <span>{ticket.customer?.name ?? "Deleted user"}</span>
        <span aria-hidden="true">·</span>
        <span>
          Opened <time dateTime={ticket.created_at}>{formatDateTime(ticket.created_at)}</time>
        </span>
        {ticket.order_number && (
          <>
            <span aria-hidden="true">·</span>
            <span>
              Order <span className="font-mono">{ticket.order_number}</span>
            </span>
          </>
        )}
      </p>
    </div>
  );
}

function PanelCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-surface rounded-2xl border border-line shadow-xs p-5">
      <h2 className="text-[11px] font-extrabold uppercase tracking-wider text-ink-muted mb-3">{title}</h2>
      {children}
    </section>
  );
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-line last:border-0 text-xs">
      <dt className="text-ink-muted shrink-0">{label}</dt>
      <dd className="text-ink text-right min-w-0 break-words">{children}</dd>
    </div>
  );
}

function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-2 text-[11px] font-semibold text-danger">
      {message}
    </p>
  );
}

function StatusCard({
  ticket,
  canManage,
  onRequest,
}: {
  ticket: AdminSupportTicketDetail;
  canManage: boolean;
  onRequest: (status: SupportStatus) => void;
}) {
  const targets = ticket.allowed_transitions.filter((status) => STATUS_ACTIONS[status]);
  return (
    <PanelCard title="Status">
      <div className="flex flex-wrap items-center gap-2">
        <AdminStatusBadge status={ticket.status} label={ticket.status_label} />
        {ticket.needs_reply && <NeedsReplyMarker />}
      </div>
      {canManage && targets.length > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-2">
          {targets.map((status) => {
            const action = STATUS_ACTIONS[status]!;
            return (
              <button
                key={status}
                type="button"
                onClick={() => onRequest(status)}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                  action.destructive
                    ? "border-danger/30 text-danger hover:bg-danger/10"
                    : status === "RESOLVED"
                      ? "border-success/30 text-success hover:bg-success/10"
                      : "border-line text-ink hover:bg-surface-alt"
                }`}
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                  {action.icon}
                </span>
                {action.label}
              </button>
            );
          })}
        </div>
      )}
      {ticket.status === "CLOSED" && (
        <p className="mt-2 text-[11px] text-ink-muted">
          Closed tickets can&apos;t be reopened. Internal notes can still be added.
        </p>
      )}
    </PanelCard>
  );
}

function DetailsCard({
  ticket,
  canManage,
  onUpdate,
}: {
  ticket: AdminSupportTicketDetail;
  canManage: boolean;
  onUpdate: (update: AdminSupportTicketUpdate, done: string) => Promise<void>;
}) {
  const priorityId = useId();
  const categoryId = useId();
  // While a change is saving, show the new value rather than flicking back.
  const [pending, setPending] = useState<{ priority?: SupportPriority; category?: SupportCategory } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const change = async (update: { priority?: SupportPriority; category?: SupportCategory }, done: string) => {
    setPending(update);
    setError(null);
    try {
      await onUpdate(update, done);
    } catch (err) {
      setError(messageOf(err, "The change couldn't be saved."));
    } finally {
      setPending(null);
    }
  };

  if (!canManage) {
    return (
      <PanelCard title="Details">
        <dl>
          <InfoRow label="Priority">
            <AdminStatusBadge status={ticket.priority} label={ticket.priority_label} size="sm" />
          </InfoRow>
          <InfoRow label="Category">{ticket.category_label}</InfoRow>
        </dl>
      </PanelCard>
    );
  }

  return (
    <PanelCard title="Details">
      <div className="space-y-3">
        <div>
          <label htmlFor={priorityId} className="block text-[11px] font-semibold text-ink-muted mb-1">
            Priority
          </label>
          <select
            id={priorityId}
            value={pending?.priority ?? ticket.priority}
            disabled={pending !== null}
            onChange={(e) => {
              const priority = e.target.value as SupportPriority;
              change({ priority }, `Priority changed to ${SUPPORT_PRIORITY_LABELS[priority]}.`);
            }}
            className={CONTROL_CLASS}
          >
            {[...SUPPORT_PRIORITIES].reverse().map((priority) => (
              <option key={priority} value={priority}>
                {SUPPORT_PRIORITY_LABELS[priority]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={categoryId} className="block text-[11px] font-semibold text-ink-muted mb-1">
            Category
          </label>
          <select
            id={categoryId}
            value={pending?.category ?? ticket.category}
            disabled={pending !== null}
            onChange={(e) => {
              const category = e.target.value as SupportCategory;
              const label = SUPPORT_CATEGORIES.find((c) => c.value === category)?.label ?? category;
              change({ category }, `Category changed to ${label}.`);
            }}
            className={CONTROL_CLASS}
          >
            {SUPPORT_CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>
                {category.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="mt-2 text-[11px] text-ink-faint">Saved as soon as you choose; the customer never sees these.</p>
      <InlineError message={error} />
    </PanelCard>
  );
}

function AssigneeCard({
  ticket,
  canManage,
  assignees,
  viewerId,
  viewerAssignable,
  onAssign,
}: {
  ticket: AdminSupportTicketDetail;
  canManage: boolean;
  assignees: AdminSupportAssignee[];
  viewerId: number | null;
  viewerAssignable: boolean;
  onAssign: (assigneeId: number | null, done: string) => Promise<void>;
}) {
  const selectId = useId();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentId = ticket.assigned_to ? String(ticket.assigned_to.id) : "";
  const options = assignees.map((agent) => ({
    value: String(agent.id),
    label: agent.id === viewerId ? `${agent.name} (you)` : agent.name,
  }));
  // Someone no longer on the assignable list still shows as the current owner.
  if (ticket.assigned_to && !options.some((option) => option.value === currentId)) {
    options.push({ value: currentId, label: ticket.assigned_to.name });
  }

  const assignTo = async (value: string) => {
    if (value === currentId) return;
    const name = value ? options.find((option) => option.value === value)?.label.replace(/ \(you\)$/, "") : null;
    setPendingId(value);
    setError(null);
    try {
      await onAssign(value ? Number(value) : null, name ? `Assigned to ${name}.` : "Unassigned.");
    } catch (err) {
      setError(messageOf(err, "The ticket couldn't be assigned."));
    } finally {
      setPendingId(null);
    }
  };

  if (!canManage) {
    return (
      <PanelCard title="Assignee">
        <p className="text-xs text-ink">
          {ticket.assigned_to ? (
            <>
              {ticket.assigned_to.name}
              {ticket.assigned_to.id === viewerId && <span className="text-ink-muted"> (you)</span>}
            </>
          ) : (
            <span className="italic text-ink-faint">Unassigned</span>
          )}
        </p>
      </PanelCard>
    );
  }

  const showAssignToMe = viewerAssignable && viewerId !== null && ticket.assigned_to?.id !== viewerId;
  return (
    <PanelCard title="Assignee">
      <label htmlFor={selectId} className="sr-only">
        Assignee
      </label>
      <select
        id={selectId}
        value={pendingId ?? currentId}
        disabled={pendingId !== null}
        onChange={(e) => assignTo(e.target.value)}
        className={CONTROL_CLASS}
      >
        <option value="">Unassigned</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {showAssignToMe && (
        <button
          type="button"
          onClick={() => assignTo(String(viewerId))}
          disabled={pendingId !== null}
          className="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-primary/30 text-primary hover:bg-primary/10 text-xs font-bold transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            assignment_ind
          </span>
          Assign to me
        </button>
      )}
      <InlineError message={error} />
    </PanelCard>
  );
}

function CustomerCard({
  customer,
  canOpenProfile,
}: {
  customer: AdminSupportCustomerDetail | null;
  canOpenProfile: boolean;
}) {
  return (
    <PanelCard title="Customer">
      {customer ? (
        <>
          <dl>
            <InfoRow label="Name">{customer.name}</InfoRow>
            <InfoRow label="Username">
              <span className="font-mono text-[11px]">{customer.username}</span>
            </InfoRow>
            <InfoRow label="Email">{customer.email || "—"}</InfoRow>
            <InfoRow label="Phone">{customer.phone || "—"}</InfoRow>
          </dl>
          {canOpenProfile && customer.customer_profile_id !== null && (
            <Link
              href={`/admin/customers/${customer.customer_profile_id}`}
              className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
            >
              Open customer profile
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                arrow_forward
              </span>
            </Link>
          )}
        </>
      ) : (
        <p className="text-xs italic text-ink-muted">This customer&apos;s account was deleted.</p>
      )}
    </PanelCard>
  );
}

function OrderCard({
  order,
  canOpenOrder,
}: {
  order: AdminSupportTicketDetail["order"];
  canOpenOrder: boolean;
}) {
  return (
    <PanelCard title="Linked order">
      {order ? (
        <dl>
          <InfoRow label="Order">
            {canOpenOrder ? (
              <Link
                href={`/admin/orders/${order.id}`}
                className="font-mono text-[11px] font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
              >
                {order.order_number}
              </Link>
            ) : (
              <span className="font-mono text-[11px]">{order.order_number}</span>
            )}
          </InfoRow>
          <InfoRow label="Status">
            <AdminStatusBadge status={order.status} size="sm" />
          </InfoRow>
          <InfoRow label="Total">
            <span className="font-bold">{formatTaka(order.total_amount)}</span>
          </InfoRow>
          <InfoRow label="Placed">{formatDateTime(order.created_at)}</InfoRow>
        </dl>
      ) : (
        <p className="text-xs text-ink-muted">Not linked to an order.</p>
      )}
    </PanelCard>
  );
}

function TimelineCard({ ticket }: { ticket: AdminSupportTicketDetail }) {
  const rows: [string, string | null][] = [
    ["Opened", ticket.created_at],
    ["First response", ticket.first_response_at],
    ["Last customer message", ticket.last_customer_message_at],
    ["Last staff reply", ticket.last_staff_reply_at],
    ["Resolved", ticket.resolved_at],
    ["Closed", ticket.closed_at],
  ];
  return (
    <PanelCard title="Timeline">
      <dl>
        {rows.map(([label, value]) => (
          <InfoRow key={label} label={label}>
            {value ? (
              <time dateTime={value}>{formatDateTime(value)}</time>
            ) : (
              <span className="text-ink-faint">—</span>
            )}
          </InfoRow>
        ))}
      </dl>
    </PanelCard>
  );
}

// =============================================================================
// COMPOSER
// =============================================================================

type ComposerMode = "reply" | "note";

function StaffComposer({
  ticket,
  canManage,
  onSend,
}: {
  ticket: AdminSupportTicketDetail;
  canManage: boolean;
  onSend: (input: AdminSupportMessageInput) => Promise<void>;
}) {
  const baseId = useId();
  const bodyId = `${baseId}-body`;
  const statusId = `${baseId}-status`;
  const closed = ticket.status === "CLOSED";

  const [mode, setMode] = useState<ComposerMode>(() => (ticket.status === "CLOSED" ? "note" : "reply"));
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [setStatus, setSetStatus] = useState<SupportStatus | "">("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const note = mode === "note";
  const replyBlocked = !note && closed;
  // A first reply moves an OPEN ticket to In progress by itself, and closing is
  // left to the Status panel, where it has a confirm step.
  const statusOptions =
    canManage && !note && !closed
      ? ticket.allowed_transitions.filter(
          (status) => status !== "CLOSED" && !(ticket.status === "OPEN" && status === "IN_PROGRESS")
        )
      : [];
  const chosenStatus = setStatus && statusOptions.includes(setStatus) ? setStatus : "";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (sending || replyBlocked) return;
    const text = body.trim();
    if (!text && files.length === 0) {
      setError("Write a message or attach a file.");
      return;
    }
    setError(null);
    setSending(true);
    try {
      await onSend({ body: text, isInternal: note, setStatus: chosenStatus || undefined, files });
      setBody("");
      setFiles([]);
      setSetStatus("");
    } catch (err) {
      setError(messageOf(err, note ? "The note couldn't be added." : "The reply couldn't be sent."));
    } finally {
      setSending(false);
    }
  };

  const modes: { value: ComposerMode; label: string; icon: string; disabled: boolean }[] = [
    { value: "reply", label: "Reply to customer", icon: "reply", disabled: closed },
    { value: "note", label: "Internal note", icon: "lock", disabled: false },
  ];

  return (
    <form
      onSubmit={submit}
      noValidate
      className={`rounded-2xl border shadow-xs p-4 sm:p-5 space-y-3 transition-colors ${
        note ? "bg-accent/5 border-dashed border-accent/50" : "bg-surface border-line"
      }`}
    >
      <fieldset>
        <legend className="sr-only">Message type</legend>
        <div className="inline-flex flex-wrap gap-1 p-1 rounded-xl bg-surface-alt border border-line">
          {modes.map((option) => {
            const selected = mode === option.value;
            return (
              <label
                key={option.value}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-primary ${
                  option.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
                } ${
                  selected
                    ? option.value === "note"
                      ? "bg-accent text-on-accent shadow-xs"
                      : "bg-primary text-on-primary shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <input
                  type="radio"
                  name={`${baseId}-mode`}
                  value={option.value}
                  checked={selected}
                  disabled={option.disabled || sending}
                  onChange={() => setMode(option.value)}
                  className="sr-only"
                />
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  {option.icon}
                </span>
                {option.label}
              </label>
            );
          })}
        </div>
      </fieldset>

      {replyBlocked ? (
        <p role="alert" className="text-xs font-semibold text-danger">
          This ticket is closed, so the customer can&apos;t be replied to. You can still add an internal note.
        </p>
      ) : (
        <p className={`flex items-center gap-1.5 text-[11px] ${note ? "text-accent font-semibold" : "text-ink-muted"}`}>
          <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
            {note ? "visibility_off" : "visibility"}
          </span>
          {note
            ? "Only the team sees internal notes. The customer is never shown this."
            : "The customer sees this reply in their ticket."}
        </p>
      )}

      {error && (
        <div
          id={`${baseId}-error`}
          role="alert"
          className="flex items-start gap-2 p-3 rounded-lg border border-danger/40 bg-danger/10 text-xs text-danger"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[16px] shrink-0">
            error
          </span>
          <p>{error}</p>
        </div>
      )}

      <div>
        <div className="flex items-baseline justify-between gap-2 mb-1">
          <label htmlFor={bodyId} className="text-xs font-bold text-ink">
            {note ? "Internal note" : "Reply"}
          </label>
          <span className="text-[11px] text-ink-faint" aria-hidden="true">
            {body.length}/{SUPPORT_LIMITS.messageMax}
          </span>
        </div>
        <textarea
          id={bodyId}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          maxLength={SUPPORT_LIMITS.messageMax}
          rows={5}
          disabled={sending}
          placeholder={note ? "Write a note for the team…" : "Write your reply to the customer…"}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${baseId}-error` : undefined}
          className={`w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint resize-y min-h-28 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-60 ${
            error ? "border-danger" : "border-line"
          }`}
        />
        <p className="mt-1 text-[11px] text-ink-faint">Ctrl + Enter sends.</p>
      </div>

      <AttachmentPicker files={files} onChange={setFiles} disabled={sending} />

      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 pt-3 border-t border-line">
        {statusOptions.length > 0 ? (
          <div className="sm:w-60">
            <label htmlFor={statusId} className="block text-[11px] font-semibold text-ink-muted mb-1">
              …and set status to
            </label>
            <select
              id={statusId}
              value={chosenStatus}
              disabled={sending}
              onChange={(e) => setSetStatus(e.target.value as SupportStatus | "")}
              className={CONTROL_CLASS}
            >
              <option value="">
                {ticket.status === "OPEN" ? "In progress (default)" : `Keep ${STAFF_STATUS_LABELS[ticket.status]}`}
              </option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {STAFF_STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span />
        )}
        <button
          type="submit"
          disabled={sending || replyBlocked}
          className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider shadow-xs transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
            note ? "bg-accent hover:bg-accent-hover text-on-accent" : "bg-primary hover:bg-primary-hover text-on-primary"
          }`}
        >
          <span aria-hidden="true" className={`material-symbols-outlined text-[18px] ${sending ? "animate-spin" : ""}`}>
            {sending ? "progress_activity" : note ? "note_add" : "send"}
          </span>
          {sending ? "Sending…" : note ? "Add internal note" : "Send reply"}
        </button>
      </div>
    </form>
  );
}
