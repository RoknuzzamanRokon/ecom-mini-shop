"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminAuditLog, getAdminAuditLogs } from "@/lib/admin-api";
import { formatDateTime, humanizeToken } from "@/lib/admin-format";
import {
  AdminDataTable,
  AdminDateField,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatusBadge,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  AUDIT_TARGET_TYPE_OPTIONS,
  AuditLogAccessNotice,
  auditActionTone,
  auditActorName,
  auditLogReason,
  auditTargetTypeLabel,
  canViewAdminAuditLogs,
} from "./auditLogGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

export default function AdminAuditLogsPage() {
  return (
    <Suspense fallback={<AuditLogsPageFallback />}>
      <AdminAuditLogsPageContent />
    </Suspense>
  );
}

function AuditLogsPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminAuditLogsPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminAuditLogs(user);

  /**
   * Five of the thirteen parameters getAdminAuditLogs accepts. The remaining
   * eight — search, resource_type (a server-side alias of target_type),
   * resource_id/target_id, shop_id, seller_id and page_size — are deliberately
   * deferred; shop_id and seller_id in particular would need a shop and seller
   * picker to be usable, which is a module of its own.
   */
  const urlActor = searchParams.get("actor") ?? "";
  const urlAction = searchParams.get("action") ?? "";
  const urlTargetType = searchParams.get("target_type") ?? "";
  const urlStartDate = searchParams.get("start_date") ?? "";
  const urlEndDate = searchParams.get("end_date") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed into the URL (and the
  // actual filter) after a short debounce so we don't fire a request per
  // keystroke. Resynced from the URL during render (not an effect) whenever it
  // changes externally — e.g. browser back/forward or "Clear filters".
  const [actorInput, setActorInput] = useState(urlActor);
  const [actionInput, setActionInput] = useState(urlAction);
  const [syncedUrlActor, setSyncedUrlActor] = useState(urlActor);
  const [syncedUrlAction, setSyncedUrlAction] = useState(urlAction);
  if (urlActor !== syncedUrlActor) {
    setSyncedUrlActor(urlActor);
    setActorInput(urlActor);
  }
  if (urlAction !== syncedUrlAction) {
    setSyncedUrlAction(urlAction);
    setActionInput(urlAction);
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
      if (actorInput !== urlActor) {
        updateParams({ actor: actorInput || null, page: null });
      }
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actorInput]);

  useEffect(() => {
    const handle = setTimeout(() => {
      if (actionInput !== urlAction) {
        updateParams({ action: actionInput || null, page: null });
      }
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionInput]);

  const [logs, setLogs] = useState<AdminAuditLog[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchLogs = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminAuditLogs(token, {
        actor: urlActor || undefined,
        action: urlAction || undefined,
        target_type: urlTargetType || undefined,
        start_date: urlStartDate || undefined,
        end_date: urlEndDate || undefined,
        page: urlPage,
      });
      setLogs(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setLogs([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load audit logs."));
    } finally {
      setLoading(false);
    }
  }, [urlActor, urlAction, urlTargetType, urlStartDate, urlEndDate, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchLogs();
  }, [canView, fetchLogs]);

  const isFiltered = Boolean(
    urlActor || urlAction || urlTargetType || urlStartDate || urlEndDate
  );
  const clearFilters = useCallback(() => {
    setActorInput("");
    setActionInput("");
    updateParams({
      actor: null,
      action: null,
      target_type: null,
      start_date: null,
      end_date: null,
      page: null,
    });
  }, [updateParams]);

  const columns: AdminTableColumn<AdminAuditLog>[] = useMemo(
    () => [
      {
        key: "when",
        header: "When",
        render: (log) => (
          <span className="block tabular-nums whitespace-nowrap">
            {formatDateTime(log.created_at)}
          </span>
        ),
        width: "w-44",
      },
      {
        key: "actor",
        header: "Actor",
        render: (log) => (
          <span className="block">
            <span className="block font-bold text-ink line-clamp-1">{auditActorName(log)}</span>
            {log.actor && (
              <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
                @{log.actor.username}
              </span>
            )}
          </span>
        ),
        width: "w-44",
      },
      {
        key: "action",
        header: "Action",
        render: (log) => (
          <AdminStatusBadge
            status={null}
            label={humanizeToken(log.action)}
            tone={auditActionTone(log.action)}
          />
        ),
      },
      {
        key: "target",
        header: "Target",
        render: (log) => (
          <span className="block">
            <span className="block font-semibold text-ink line-clamp-1">
              {auditTargetTypeLabel(log.target_type)}
              {log.target_id ? (
                <span className="font-mono text-[11px] font-medium text-ink-muted"> #{log.target_id}</span>
              ) : null}
            </span>
            {log.target_repr && (
              <span className="block text-[11px] font-medium text-ink-muted line-clamp-1">
                {log.target_repr}
              </span>
            )}
          </span>
        ),
        hideOnMobile: true,
      },
      {
        key: "reason",
        header: "Reason",
        render: (log) => {
          const reason = auditLogReason(log);
          return reason ? (
            <span className="block line-clamp-2" title={reason}>
              {reason}
            </span>
          ) : (
            "—"
          );
        },
        hideOnMobile: true,
      },
      {
        key: "ip",
        header: "IP Address",
        render: (log) => (
          <span className="block font-mono text-[11px] whitespace-nowrap">
            {log.ip_address || "—"}
          </span>
        ),
        hideOnMobile: true,
        width: "w-32",
      },
    ],
    []
  );

  if (!canView) {
    return <AuditLogAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Audit Logs</h1>
          <p className="text-xs text-ink-muted">
            Immutable governance and state-transition history. Entries can be read and filtered
            only — this module never edits, annotates or removes an audit record.
          </p>
        </div>
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} entr{totalCount === 1 ? "y" : "ies"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Actor"
          placeholder="User ID, username or email…"
          value={actorInput}
          onChange={setActorInput}
          className="sm:w-60"
        />
        <AdminSearchField
          label="Action"
          placeholder="e.g. SELLER, PAYMENT, DELETED…"
          value={actionInput}
          onChange={setActionInput}
          className="sm:w-60"
        />
        <AdminSelectField
          label="Target type"
          value={urlTargetType}
          options={AUDIT_TARGET_TYPE_OPTIONS}
          onChange={(value) => updateParams({ target_type: value || null, page: null })}
        />
        <AdminDateField
          label="From"
          value={urlStartDate}
          max={urlEndDate || undefined}
          onChange={(value) => updateParams({ start_date: value || null, page: null })}
        />
        <AdminDateField
          label="To"
          value={urlEndDate}
          min={urlStartDate || undefined}
          onChange={(value) => updateParams({ end_date: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminAuditLog>
        caption="Platform governance audit history"
        columns={columns}
        rows={logs}
        getRowId={(log) => log.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchLogs}
        emptyTitle="No audit entries found"
        emptyMessage={
          isFiltered
            ? "No audit entries match the current filters."
            : "No audit entries have been recorded yet."
        }
        emptyIcon="history"
        emptyAction={
          isFiltered ? (
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
