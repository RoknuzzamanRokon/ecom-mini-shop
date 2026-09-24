"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminSupportAssignee,
  AdminSupportSummary,
  AdminSupportTicket,
  getAdminSupportAssignees,
  getAdminSupportSummary,
  getAdminSupportTickets,
} from "@/lib/admin-api";
import { formatDateTime } from "@/lib/admin-format";
import { formatRelativeTime } from "@/lib/support";
import type { PaginatedResponse } from "@/lib/types";
import {
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatCard,
  AdminStatusBadge,
  type AdminSelectOption,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  CATEGORY_OPTIONS,
  DEFAULT_ORDERING,
  ORDERING_OPTIONS,
  PRIORITY_OPTIONS,
  QUEUE_VIEWS,
  SUPPORT_STATUS_TABS,
  SupportAccessNotice,
  canViewSupport,
  parseAssigned,
  parseCategory,
  parseOrdering,
  parsePriority,
  parseStatusTab,
  type SupportStatusTab,
} from "./supportGovernance";

/** Matches StaffTicketPagination.page_size in support/views.py. */
const PAGE_SIZE = 20;

const NO_SESSION = "No active session token was found. Please sign in again.";

export default function AdminSupportPage() {
  return (
    <Suspense fallback={<SupportPageFallback />}>
      <AdminSupportPageContent />
    </Suspense>
  );
}

function SupportPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

/** A fetch result, stored with the key of the request that produced it. */
interface ListState {
  key: string;
  data?: PaginatedResponse<AdminSupportTicket>;
  error?: string;
  /** When it arrived; "5 min ago" is measured from here, keeping render pure. */
  loadedAt: number;
}

function ticketHref(ticket: AdminSupportTicket): string {
  return `/admin/support/${encodeURIComponent(ticket.ticket_number)}`;
}

function AdminSupportPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewSupport(user);

  const urlStatus = parseStatusTab(searchParams.get("status"));
  const urlPriority = parsePriority(searchParams.get("priority"));
  const urlCategory = parseCategory(searchParams.get("category"));
  const urlAssigned = parseAssigned(searchParams.get("assigned"));
  const urlNeedsReply = searchParams.get("needs_reply") === "true";
  const urlOrdering = parseOrdering(searchParams.get("ordering"));
  const urlSearch = searchParams.get("search") ?? "";
  const urlPage = Math.max(Number.parseInt(searchParams.get("page") ?? "1", 10) || 1, 1);

  // Local text state so typing feels instant; committed to the URL after a
  // short debounce, and resynced from the URL during render when it changes
  // externally (back/forward, a queue card, "Clear").
  const [searchInput, setSearchInput] = useState(urlSearch);
  const [syncedUrlSearch, setSyncedUrlSearch] = useState(urlSearch);
  if (urlSearch !== syncedUrlSearch) {
    setSyncedUrlSearch(urlSearch);
    setSearchInput(urlSearch);
  }

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([key, value]) => {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      });
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [searchParams, router, pathname]
  );

  useEffect(() => {
    const handle = setTimeout(() => {
      if (searchInput !== urlSearch) updateParams({ search: searchInput || null, page: null });
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput, urlSearch, updateParams]);

  // Refresh reloads the list and the counts; there is no polling on this page.
  const [reloadToken, setReloadToken] = useState(0);

  const [list, setList] = useState<ListState | null>(null);
  const requestKey = [
    urlStatus,
    urlPriority,
    urlCategory,
    urlAssigned,
    urlNeedsReply,
    urlOrdering,
    urlSearch,
    urlPage,
    reloadToken,
  ].join("|");

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    const token = getAuthToken();
    const request = token
      ? getAdminSupportTickets(token, {
          status: urlStatus,
          priority: urlPriority || undefined,
          category: urlCategory || undefined,
          assigned: urlAssigned || undefined,
          needs_reply: urlNeedsReply || undefined,
          search: urlSearch || undefined,
          ordering: urlOrdering === DEFAULT_ORDERING ? undefined : urlOrdering,
          page: urlPage,
        })
      : Promise.reject(new Error(NO_SESSION));
    request
      .then((data) => {
        if (!cancelled) setList({ key: requestKey, data, loadedAt: Date.now() });
      })
      .catch((err) => {
        if (!cancelled) {
          setList({
            key: requestKey,
            error: err instanceof Error ? err.message : "Failed to load support tickets.",
            loadedAt: Date.now(),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    canView,
    requestKey,
    urlStatus,
    urlPriority,
    urlCategory,
    urlAssigned,
    urlNeedsReply,
    urlOrdering,
    urlSearch,
    urlPage,
  ]);

  // The counts behind the cards and tabs. A refresh keeps the old numbers on
  // screen until the new ones arrive.
  const [summary, setSummary] = useState<{ data?: AdminSupportSummary; failed?: boolean } | null>(null);
  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    const token = getAuthToken();
    (token ? getAdminSupportSummary(token) : Promise.reject(new Error(NO_SESSION)))
      .then((data) => {
        if (!cancelled) setSummary({ data });
      })
      .catch(() => {
        if (!cancelled) setSummary((prev) => (prev?.data ? prev : { failed: true }));
      });
    return () => {
      cancelled = true;
    };
  }, [canView, reloadToken]);

  // Everyone a ticket can be assigned to, for the Assignee filter. Without it
  // the filter still offers Anyone / Me / Unassigned.
  const [assignees, setAssignees] = useState<AdminSupportAssignee[]>([]);
  useEffect(() => {
    if (!canView) return;
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
  }, [canView]);

  const loading = list?.key !== requestKey;
  const tickets = !loading ? list?.data?.results ?? [] : [];
  const totalCount = !loading ? list?.data?.count ?? 0 : 0;
  const error = !loading ? list?.error ?? null : null;
  const loadedAt = list?.loadedAt ?? 0;

  const hasFilters = Boolean(urlSearch || urlPriority || urlCategory || urlAssigned || urlNeedsReply);
  const isDirty = hasFilters || urlOrdering !== DEFAULT_ORDERING;
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({
      search: null,
      priority: null,
      category: null,
      assigned: null,
      needs_reply: null,
      ordering: null,
      page: null,
    });
  }, [updateParams]);

  const userId = user?.id;
  const assigneeOptions: AdminSelectOption[] = useMemo(() => {
    const options: AdminSelectOption[] = [
      { value: "me", label: "Me" },
      { value: "unassigned", label: "Unassigned" },
      ...assignees.map((agent) => ({
        value: String(agent.id),
        label: agent.id === userId ? `${agent.name} (you)` : agent.name,
      })),
    ];
    // A link to someone no longer assignable still shows who it filters by.
    if (/^\d+$/.test(urlAssigned) && !options.some((option) => option.value === urlAssigned)) {
      options.push({ value: urlAssigned, label: `User #${urlAssigned}` });
    }
    return options;
  }, [assignees, urlAssigned, userId]);

  const summaryData = summary?.data;
  const tabCount = (tab: SupportStatusTab): number | null => {
    if (!summaryData) return null;
    if (tab === "active") return summaryData.active;
    if (tab === "all") return Object.values(summaryData.by_status).reduce((sum, n) => sum + n, 0);
    return summaryData.by_status[tab] ?? 0;
  };

  // Which queue card matches what the list shows now (sorting aside).
  const currentView: Record<string, string> = {
    status: urlStatus === "active" ? "" : urlStatus,
    priority: urlPriority,
    category: urlCategory,
    assigned: urlAssigned,
    needs_reply: urlNeedsReply ? "true" : "",
    search: urlSearch,
  };
  const isCurrentView = (params: Record<string, string>) =>
    Object.keys(currentView).every((key) => (params[key] ?? "") === currentView[key]);
  const viewHref = (params: Record<string, string>) => {
    const query = new URLSearchParams(params);
    if (urlOrdering !== DEFAULT_ORDERING) query.set("ordering", urlOrdering);
    return `${pathname}?${query.toString()}`;
  };

  const columns: AdminTableColumn<AdminSupportTicket>[] = useMemo(
    () => [
      {
        key: "needs_reply",
        header: <span className="sr-only">Needs reply</span>,
        render: (ticket) =>
          ticket.needs_reply ? (
            <span className="flex justify-center" title="Needs reply">
              <span aria-hidden="true" className="w-2.5 h-2.5 rounded-full bg-accent" />
              <span className="sr-only">Needs reply</span>
            </span>
          ) : null,
        width: "w-10",
        className: "pr-0",
        headerClassName: "pr-0",
      },
      {
        key: "subject",
        header: "Ticket",
        render: (ticket) => (
          <div className="min-w-0">
            <Link
              href={ticketHref(ticket)}
              className={`line-clamp-2 text-ink hover:text-primary transition-colors rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                ticket.needs_reply ? "font-extrabold" : "font-bold"
              }`}
            >
              {ticket.subject}
            </Link>
            <span className="block text-[11px] text-ink-muted">
              <span className="font-mono">{ticket.ticket_number}</span>
              {" · "}
              {ticket.customer?.name ?? "Deleted user"}
            </span>
            {/* Phones: the columns below are hidden, so their essentials go here. */}
            <span className="mt-1.5 flex flex-wrap items-center gap-1.5 sm:hidden">
              <AdminStatusBadge status={ticket.priority} label={ticket.priority_label} size="sm" />
              <AdminStatusBadge status={ticket.status} label={ticket.status_label} size="sm" />
              <time dateTime={ticket.last_activity_at} className="text-[11px] text-ink-muted">
                {formatRelativeTime(ticket.last_activity_at, loadedAt)}
              </time>
            </span>
          </div>
        ),
        className: "min-w-48",
      },
      {
        key: "category",
        header: "Category",
        render: (ticket) => ticket.category_label,
        hideOnMobile: true,
      },
      {
        key: "priority",
        header: "Priority",
        render: (ticket) => (
          <AdminStatusBadge status={ticket.priority} label={ticket.priority_label} size="sm" />
        ),
        hideOnMobile: true,
      },
      {
        key: "status",
        header: "Status",
        render: (ticket) => <AdminStatusBadge status={ticket.status} label={ticket.status_label} />,
        hideOnMobile: true,
      },
      {
        key: "assignee",
        header: "Assignee",
        render: (ticket) =>
          ticket.assigned_to ? (
            <span>
              {ticket.assigned_to.name}
              {ticket.assigned_to.id === userId && <span className="text-ink-muted"> (you)</span>}
            </span>
          ) : (
            <span className="italic text-ink-faint">Unassigned</span>
          ),
        hideOnMobile: true,
      },
      {
        key: "activity",
        header: "Last activity",
        render: (ticket) => (
          <time
            dateTime={ticket.last_activity_at}
            title={formatDateTime(ticket.last_activity_at)}
            className="whitespace-nowrap text-ink-muted"
          >
            {formatRelativeTime(ticket.last_activity_at, loadedAt)}
          </time>
        ),
        hideOnMobile: true,
      },
    ],
    [userId, loadedAt]
  );

  if (!canView) {
    return <SupportAccessNotice />;
  }

  const tabLabel = SUPPORT_STATUS_TABS.find((tab) => tab.value === urlStatus)?.label ?? "";
  const emptyTitle = hasFilters
    ? "No tickets found"
    : urlStatus === "active"
      ? "The queue is clear"
      : "No tickets here";
  const emptyMessage = hasFilters
    ? "No tickets match the current filters."
    : urlStatus === "active"
      ? "There are no active tickets right now. New customer tickets appear here."
      : urlStatus === "all"
        ? "No customer has opened a ticket yet."
        : `No tickets are ${tabLabel.toLowerCase()} right now.`;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Support Tickets</h1>
          <p className="text-xs text-ink-muted">
            Customer problems waiting on the team. Open a ticket to reply, write internal notes, assign it
            and move it through to resolved.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReloadToken((t) => t + 1)}
          disabled={loading}
          className="self-start shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-ink text-xs font-bold transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden="true" className={`material-symbols-outlined text-[16px] ${loading ? "animate-spin" : ""}`}>
            {loading ? "progress_activity" : "refresh"}
          </span>
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {QUEUE_VIEWS.map((view) => (
          <AdminStatCard
            key={view.key}
            title={view.title}
            value={summaryData ? view.count(summaryData) : summary?.failed ? "—" : null}
            icon={view.icon}
            tone={view.tone}
            description={view.description}
            loading={!summary}
            href={viewHref(view.params)}
            active={isCurrentView(view.params)}
          />
        ))}
      </div>

      <div role="tablist" aria-label="Ticket status" className="flex flex-wrap gap-2">
        {SUPPORT_STATUS_TABS.map((tab) => {
          const selected = urlStatus === tab.value;
          const count = tabCount(tab.value);
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => updateParams({ status: tab.value === "active" ? null : tab.value, page: null })}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                selected
                  ? "bg-primary text-on-primary border-primary shadow-sm"
                  : "bg-surface text-ink border-line hover:bg-surface-alt"
              }`}
            >
              {tab.label}
              {count !== null && (
                <span
                  className={`min-w-5 px-1.5 py-px rounded-full text-[10px] tabular-nums ${
                    selected ? "bg-on-primary/20" : "bg-surface-alt text-ink-muted"
                  }`}
                >
                  {count.toLocaleString("en-US")}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <AdminFilterBar
        isDirty={isDirty}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} ticket{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Ticket no., subject, customer or order…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-80"
        />
        <AdminSelectField
          label="Priority"
          value={urlPriority}
          options={PRIORITY_OPTIONS}
          onChange={(value) => updateParams({ priority: value || null, page: null })}
          className="sm:w-32"
        />
        <AdminSelectField
          label="Category"
          value={urlCategory}
          options={CATEGORY_OPTIONS}
          onChange={(value) => updateParams({ category: value || null, page: null })}
        />
        <AdminSelectField
          label="Assignee"
          value={urlAssigned}
          options={assigneeOptions}
          placeholder="Anyone"
          onChange={(value) => updateParams({ assigned: value || null, page: null })}
        />
        <AdminSelectField
          label="Sort by"
          value={urlOrdering}
          options={ORDERING_OPTIONS}
          placeholder={null}
          onChange={(value) =>
            updateParams({ ordering: value === DEFAULT_ORDERING ? null : value, page: null })
          }
          className="sm:w-40"
        />
        <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-xs font-semibold text-ink whitespace-nowrap cursor-pointer select-none transition-colors">
          <input
            type="checkbox"
            checked={urlNeedsReply}
            onChange={(e) => updateParams({ needs_reply: e.target.checked ? "true" : null, page: null })}
            className="w-3.5 h-3.5 accent-primary cursor-pointer"
          />
          Needs reply only
        </label>
      </AdminFilterBar>

      <AdminDataTable<AdminSupportTicket>
        caption="Support tickets"
        columns={columns}
        rows={tickets}
        getRowId={(ticket) => ticket.ticket_number}
        loading={loading}
        error={error}
        onRetry={() => setReloadToken((t) => t + 1)}
        emptyIcon="support_agent"
        emptyTitle={emptyTitle}
        emptyMessage={emptyMessage}
        emptyAction={
          hasFilters ? (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Clear filters
            </button>
          ) : undefined
        }
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />
    </div>
  );
}
