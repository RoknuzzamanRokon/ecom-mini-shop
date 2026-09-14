"use client";

import React from "react";
import AdminPagination from "./AdminPagination";

/**
 * A column definition for AdminDataTable.
 * `render` receives the whole row so cells can compose badges, links, or actions.
 */
export interface AdminTableColumn<T> {
  /** Stable key, unique within the column set. */
  key: string;
  header: React.ReactNode;
  render: (row: T, rowIndex: number) => React.ReactNode;
  align?: "left" | "center" | "right";
  /** Collapses the column below the `sm` breakpoint to keep narrow screens readable. */
  hideOnMobile?: boolean;
  /** Tailwind width utility, e.g. "w-40". */
  width?: string;
  className?: string;
  headerClassName?: string;
}

export interface AdminRowAction<T> {
  key: string;
  label: string;
  /** Material Symbols ligature name. */
  icon?: string;
  onClick: (row: T) => void;
  tone?: "default" | "primary" | "danger";
  /**
   * Hides the action entirely — use for permissions the user does not hold,
   * so the console never advertises an operation the backend would reject.
   */
  isHidden?: (row: T) => boolean;
  /** Disables the action for rows in an invalid state (e.g. already approved). */
  isDisabled?: (row: T) => boolean;
}

export interface AdminDataTableProps<T> {
  columns: AdminTableColumn<T>[];
  rows: T[];
  /** Stable identity for React keys and row selection. */
  getRowId: (row: T) => string | number;

  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;

  /** Accessible table description; visually hidden but announced by screen readers. */
  caption: string;

  emptyTitle?: string;
  emptyMessage?: string;
  emptyIcon?: string;
  /** Rendered inside the empty state, e.g. a "Clear filters" button. */
  emptyAction?: React.ReactNode;
  skeletonRows?: number;

  actions?: AdminRowAction<T>[];
  actionsHeader?: string;

  selectable?: boolean;
  selectedIds?: Array<string | number>;
  onSelectionChange?: (ids: Array<string | number>) => void;
  isRowSelectable?: (row: T) => boolean;

  onRowClick?: (row: T) => void;

  /** Server-side pagination. Omit `onPageChange` to hide the pager. */
  page?: number;
  pageSize?: number;
  totalCount?: number;
  onPageChange?: (page: number) => void;

  className?: string;
}

const ALIGN_CLASSES: Record<NonNullable<AdminTableColumn<unknown>["align"]>, string> = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
};

const ACTION_TONE_CLASSES: Record<
  NonNullable<AdminRowAction<unknown>["tone"]>,
  string
> = {
  default: "text-ink-muted hover:text-ink hover:bg-surface-alt",
  primary: "text-primary hover:bg-primary/10",
  danger: "text-red-600 hover:bg-red-500/10",
};

/**
 * Generic, reusable management table.
 *
 * Reusable across every admin module (shops, sellers, products, orders,
 * payments, categories, customers, users, roles, audit logs) by supplying a
 * column set and row type — no domain logic lives here.
 *
 * Sorting is intentionally NOT implemented: no current admin endpoint accepts an
 * ordering parameter, and client-only sorting of a single server page would
 * mislead operators into thinking they had sorted the full result set.
 */
export default function AdminDataTable<T>({
  columns,
  rows,
  getRowId,
  loading = false,
  error = null,
  onRetry,
  caption,
  emptyTitle = "No records found",
  emptyMessage = "Nothing matches the current filters.",
  emptyIcon = "inbox",
  emptyAction,
  skeletonRows = 6,
  actions,
  actionsHeader = "Actions",
  selectable = false,
  selectedIds,
  onSelectionChange,
  isRowSelectable,
  onRowClick,
  page,
  pageSize,
  totalCount,
  onPageChange,
  className = "",
}: AdminDataTableProps<T>) {
  const hasActions = Boolean(actions && actions.length > 0);
  const selection = React.useMemo(
    () => new Set(selectedIds ?? []),
    [selectedIds]
  );

  const selectableRows = React.useMemo(
    () => (isRowSelectable ? rows.filter(isRowSelectable) : rows),
    [rows, isRowSelectable]
  );

  const allSelected =
    selectableRows.length > 0 &&
    selectableRows.every((row) => selection.has(getRowId(row)));
  const someSelected =
    !allSelected && selectableRows.some((row) => selection.has(getRowId(row)));

  const headerCheckboxRef = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  const toggleAll = () => {
    if (!onSelectionChange) return;
    if (allSelected) {
      const pageIds = new Set(selectableRows.map(getRowId));
      onSelectionChange([...selection].filter((id) => !pageIds.has(id)));
      return;
    }
    const merged = new Set(selection);
    selectableRows.forEach((row) => merged.add(getRowId(row)));
    onSelectionChange([...merged]);
  };

  const toggleRow = (row: T) => {
    if (!onSelectionChange) return;
    const id = getRowId(row);
    const next = new Set(selection);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange([...next]);
  };

  const totalColumns = columns.length + (selectable ? 1 : 0) + (hasActions ? 1 : 0);

  const headerCellClass =
    "px-4 py-3 text-[10px] font-extrabold uppercase tracking-wider text-ink-muted whitespace-nowrap";

  // ---- Error state ---------------------------------------------------------
  if (error && !loading) {
    return (
      <div
        className={`bg-surface rounded-2xl border border-line shadow-xs p-8 ${className}`}
      >
        <div role="alert" className="flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              error
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">Unable to load data</p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">{error}</p>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`bg-surface rounded-2xl border border-line shadow-xs ${className}`}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" aria-busy={loading}>
          <caption className="sr-only">{caption}</caption>

          <thead>
            <tr className="border-b border-line bg-surface-alt/50">
              {selectable && (
                <th scope="col" className={`${headerCellClass} w-10`}>
                  <input
                    ref={headerCheckboxRef}
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    disabled={loading || selectableRows.length === 0}
                    aria-label="Select all rows on this page"
                    className="w-3.5 h-3.5 rounded border-line accent-[var(--color-primary)] cursor-pointer disabled:cursor-not-allowed"
                  />
                </th>
              )}

              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`${headerCellClass} ${
                    ALIGN_CLASSES[column.align ?? "left"]
                  } ${column.width ?? ""} ${
                    column.hideOnMobile ? "hidden sm:table-cell" : ""
                  } ${column.headerClassName ?? ""}`}
                >
                  {column.header}
                </th>
              ))}

              {hasActions && (
                <th scope="col" className={`${headerCellClass} text-right`}>
                  {actionsHeader}
                </th>
              )}
            </tr>
          </thead>

          <tbody>
            {/* ---- Loading skeleton ---- */}
            {loading &&
              Array.from({ length: skeletonRows }).map((_, rowIndex) => (
                <tr key={`skeleton-${rowIndex}`} className="border-b border-line">
                  {Array.from({ length: totalColumns }).map((__, cellIndex) => (
                    <td key={`skeleton-cell-${cellIndex}`} className="px-4 py-3.5">
                      <div className="h-3.5 rounded bg-surface-alt animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))}

            {/* ---- Empty state ---- */}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={totalColumns} className="px-4 py-14">
                  <div className="flex flex-col items-center text-center gap-2">
                    <div className="w-12 h-12 rounded-2xl bg-surface-alt text-ink-muted flex items-center justify-center">
                      <span
                        aria-hidden="true"
                        className="material-symbols-outlined text-[26px]"
                      >
                        {emptyIcon}
                      </span>
                    </div>
                    <p className="text-sm font-bold text-ink">{emptyTitle}</p>
                    <p className="text-xs text-ink-muted max-w-sm">{emptyMessage}</p>
                    {emptyAction && <div className="mt-2">{emptyAction}</div>}
                  </div>
                </td>
              </tr>
            )}

            {/* ---- Data rows ---- */}
            {!loading &&
              rows.map((row, rowIndex) => {
                const id = getRowId(row);
                const isSelected = selection.has(id);
                const rowSelectable = isRowSelectable ? isRowSelectable(row) : true;
                const visibleActions =
                  actions?.filter((action) => !action.isHidden?.(row)) ?? [];

                return (
                  <tr
                    key={id}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={`border-b border-line last:border-0 transition-colors ${
                      isSelected ? "bg-primary/5" : "hover:bg-surface-alt/60"
                    } ${onRowClick ? "cursor-pointer" : ""}`}
                  >
                    {selectable && (
                      <td className="px-4 py-3.5" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleRow(row)}
                          disabled={!rowSelectable}
                          aria-label={`Select row ${id}`}
                          className="w-3.5 h-3.5 rounded border-line accent-[var(--color-primary)] cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
                        />
                      </td>
                    )}

                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`px-4 py-3.5 text-xs text-ink align-middle ${
                          ALIGN_CLASSES[column.align ?? "left"]
                        } ${column.hideOnMobile ? "hidden sm:table-cell" : ""} ${
                          column.className ?? ""
                        }`}
                      >
                        {column.render(row, rowIndex)}
                      </td>
                    ))}

                    {hasActions && (
                      <td
                        className="px-4 py-3.5 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-end gap-1">
                          {visibleActions.length === 0 && (
                            <span className="text-[11px] text-ink-faint">—</span>
                          )}
                          {visibleActions.map((action) => {
                            const disabled = action.isDisabled?.(row) ?? false;
                            return (
                              <button
                                key={action.key}
                                type="button"
                                onClick={() => action.onClick(row)}
                                disabled={disabled}
                                title={action.label}
                                aria-label={action.label}
                                className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                                  ACTION_TONE_CLASSES[action.tone ?? "default"]
                                }`}
                              >
                                {action.icon && (
                                  <span
                                    aria-hidden="true"
                                    className="material-symbols-outlined text-[16px]"
                                  >
                                    {action.icon}
                                  </span>
                                )}
                                <span className="hidden md:inline">{action.label}</span>
                              </button>
                            );
                          })}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>

      {onPageChange && page !== undefined && pageSize !== undefined && (
        <div className="px-4 pb-4">
          <AdminPagination
            page={page}
            pageSize={pageSize}
            totalCount={totalCount ?? 0}
            onPageChange={onPageChange}
            disabled={loading}
          />
        </div>
      )}
    </div>
  );
}
