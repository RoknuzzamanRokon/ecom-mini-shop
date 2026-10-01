"use client";

import React from "react";
import { formatCount, formatDate, formatDateTime } from "@/lib/admin-format";

/** One wallet movement, already mapped from a staff or seller ledger row. */
export interface PointMovementRow {
  id: number | string;
  /** Material Symbols name. */
  icon: string;
  /** What happened, e.g. "Given to Seller". */
  title: string;
  /** Who it involved, e.g. a seller's business name. */
  context?: string | null;
  reason?: string | null;
  /** Always positive; `incoming` carries the direction. */
  amount: number;
  incoming: boolean;
  balanceAfter: number;
  /** ISO timestamp. */
  when: string;
}

/** A newest-first list of wallet movements with signed amounts and the balance after each. */
export default function PointMovementList({
  rows,
  label,
}: {
  rows: PointMovementRow[];
  /** Accessible name for the list. */
  label: string;
}) {
  return (
    <ol aria-label={label} className="divide-y divide-line-subtle">
      {rows.map((row) => (
        <li key={row.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
          <span
            aria-hidden="true"
            className={`material-symbols-outlined w-10 h-10 shrink-0 rounded-xl flex items-center justify-center ${
              row.incoming ? "bg-success/10 text-success" : "bg-primary/10 text-primary"
            }`}
          >
            {row.icon}
          </span>

          <div className="min-w-0 flex-1">
            <p className="text-xs text-ink">
              <span className="font-bold">{row.title}</span>
              {row.context && <span className="text-ink-muted"> · {row.context}</span>}
            </p>
            {row.reason && (
              <p className="text-[11px] text-ink-muted mt-0.5 line-clamp-1" title={row.reason}>
                {row.reason}
              </p>
            )}
            <time
              dateTime={row.when}
              title={formatDateTime(row.when)}
              className="block text-[10px] font-semibold text-ink-faint mt-1"
            >
              {formatDate(row.when)}
            </time>
          </div>

          <div className="shrink-0 text-right">
            <p
              className={`text-sm font-black tabular-nums ${row.incoming ? "text-success" : "text-ink"}`}
            >
              <span className="sr-only">{row.incoming ? "In: " : "Out: "}</span>
              <span aria-hidden="true">{row.incoming ? "+" : "−"}</span>
              {formatCount(row.amount)}
            </p>
            <p className="text-[10px] font-semibold text-ink-muted tabular-nums mt-0.5">
              Balance {formatCount(row.balanceAfter)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
