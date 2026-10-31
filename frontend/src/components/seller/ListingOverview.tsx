"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  InsufficientPointsError,
  getSellerListingSummary,
  getSellerProducts,
  renewSellerProduct,
} from "@/lib/api";
import { formatDate } from "@/lib/admin-format";
import { getAuthToken } from "@/lib/auth";
import type { ListingFilter, ListingSummary, Product } from "@/lib/types";
import { useLatestRequest } from "@/hooks/useLatestRequest";
import { daysLeft, listingPeriodLine } from "./listing";

const TABS: { key: ListingFilter; label: string }[] = [
  { key: "ending_soon", label: "Ending soon" },
  { key: "expired", label: "Expired" },
  { key: "live", label: "Live" },
];

const ROWS = 10;

const EMPTY_TEXT: Record<ListingFilter, string> = {
  ending_soon: "Nothing ends in the next few days.",
  expired: "No product has expired.",
  live: "No product is live yet.",
};

/**
 * The seller dashboard's listing section: how many products are live, ending
 * soon, expired and in review, each product's end date, and Renew on expired
 * ones. `onRenewed` lets the page refresh what a renewal spent.
 */
export default function ListingOverview({ onRenewed }: { onRenewed?: () => void }) {
  const [summary, setSummary] = useState<ListingSummary | null>(null);
  const [tab, setTab] = useState<ListingFilter>("ending_soon");
  const [rows, setRows] = useState<Product[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [renewingId, setRenewingId] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const beginRequest = useLatestRequest();

  useEffect(() => {
    const token = getAuthToken();
    if (!token) return;
    const isLatest = beginRequest();
    Promise.all([
      getSellerListingSummary(token),
      getSellerProducts(token, { listing: tab, page: 1, page_size: ROWS }),
    ])
      .then(([nextSummary, list]) => {
        if (!isLatest()) return;
        setSummary(nextSummary);
        setRows(list.results);
        setRowCount(list.count);
        setError(null);
      })
      .catch((err: unknown) => {
        if (isLatest()) setError(err instanceof Error ? err.message : "Failed to load your listings.");
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, [tab, reloadKey, beginRequest]);

  const selectTab = (next: ListingFilter) => {
    if (next === tab) return;
    setLoading(true);
    setConfirmingId(null);
    setTab(next);
  };

  const renew = (product: Product) => {
    const token = getAuthToken();
    if (!token || renewingId !== null) return;
    setRenewingId(product.id);
    setError(null);
    setNotice(null);
    renewSellerProduct(token, product.id)
      .then((renewed) => {
        setNotice(`"${renewed.name}" is live again until ${formatDate(renewed.live_until)}.`);
        setConfirmingId(null);
        setLoading(true);
        setReloadKey((key) => key + 1);
        onRenewed?.();
      })
      .catch((err: unknown) => {
        setError(
          err instanceof InsufficientPointsError
            ? `Renewing needs ${err.requiredPoints} points and your wallet holds ${err.availablePoints}. Buy points from MiniShop staff or your Sales Team contact.`
            : err instanceof Error
            ? err.message
            : "The product could not be renewed."
        );
      })
      .finally(() => setRenewingId(null));
  };

  const allTiles = summary
    ? [
        { label: "Live", value: summary.live, hint: "On the storefront now", icon: "storefront", tone: "bg-success/10 text-success" },
        {
          label: "Ending soon",
          value: summary.ending_soon,
          hint: `Within ${summary.ending_soon_days} days`,
          icon: "schedule",
          tone: "bg-accent/10 text-accent",
        },
        { label: "Expired", value: summary.expired, hint: "Renew to go live again", icon: "event_busy", tone: "bg-danger/10 text-danger" },
        { label: "In review", value: summary.in_review, hint: "Waiting for staff", icon: "pending", tone: "bg-primary/10 text-primary" },
      ]
    : [];
  // A Full Shop Owner's products never end, so only these two apply.
  const tiles = summary?.has_end_date === false
    ? allTiles.filter((tile) => tile.label === "Live" || tile.label === "In review")
    : allTiles;

  return (
    <section className="bg-surface rounded-2xl border border-line p-6 shadow-xs space-y-4" aria-labelledby="listing-heading">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-line">
        <div>
          <h2 id="listing-heading" className="text-base font-bold text-ink">
            Product Listings
          </h2>
          <p className="text-xs text-ink-muted">
            {summary && !summary.has_end_date
              ? "As a Full Shop Owner, your products stay live with no end date."
              : summary
              ? `A new product stays live ${summary.first_period_months} months. After that, renewing costs ${summary.renewal_points} points for ${summary.renewal_period_months} more months.`
              : "How long each of your products stays live."}
          </p>
        </div>
        <Link
          href="/seller/products"
          className="text-xs font-bold uppercase tracking-wider text-primary hover:underline flex items-center gap-1 shrink-0"
        >
          <span>All Products</span>
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>
      </div>

      {error && (
        <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="p-3 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-medium">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {(summary ? tiles : TABS.map((t) => ({ label: t.label, value: null, hint: "", icon: "", tone: "" }))).map(
          (tile) => (
            <div key={tile.label} className="rounded-xl border border-line p-4 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[11px] font-bold uppercase tracking-wider text-ink-muted">{tile.label}</p>
                <p className="text-2xl font-black text-ink mt-1">{tile.value ?? "..."}</p>
                {tile.hint && <p className="text-[11px] text-ink-muted mt-0.5">{tile.hint}</p>}
              </div>
              {tile.icon && (
                <div className={`w-10 h-10 rounded-lg hidden sm:flex items-center justify-center shrink-0 ${tile.tone}`}>
                  <span aria-hidden="true" className="material-symbols-outlined">
                    {tile.icon}
                  </span>
                </div>
              )}
            </div>
          )
        )}
      </div>

      {summary?.has_end_date !== false && (
        <div>
          <div role="tablist" aria-label="Listing lists" className="flex flex-wrap gap-2 mb-3">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => selectTab(t.key)}
                className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-colors cursor-pointer ${
                  tab === t.key
                    ? "bg-primary text-on-primary border-primary"
                    : "bg-surface text-ink-muted border-line hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {loading ? (
            <p className="py-6 text-center text-xs text-ink-muted">Loading listings...</p>
          ) : rows.length === 0 ? (
            <p className="py-6 text-center text-xs text-ink-muted">{EMPTY_TEXT[tab]}</p>
          ) : (
            <ul className="divide-y divide-line-subtle">
              {rows.map((product) => {
                const left = product.status === "PUBLISHED" && product.live_until ? daysLeft(product.live_until) : null;
                return (
                  <li key={product.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-ink truncate">{product.name}</p>
                      <p className="text-[11px] text-ink-muted mt-0.5">
                        {listingPeriodLine(product)}
                        {left !== null && ` · ${left} day${left === 1 ? "" : "s"} left`}
                        {" · "}
                        {product.in_stock ? `${product.stock} in stock` : "Out of stock"}
                      </p>
                    </div>
                    {product.status === "EXPIRED" && summary && (
                      <div className="flex items-center gap-2 shrink-0">
                        {confirmingId === product.id ? (
                          <>
                            <span className="text-[11px] text-ink-muted">
                              Renew for {summary.renewal_points} points?
                            </span>
                            <button
                              type="button"
                              onClick={() => renew(product)}
                              disabled={renewingId !== null}
                              className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                            >
                              {renewingId === product.id ? "Renewing..." : "Confirm"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmingId(null)}
                              disabled={renewingId !== null}
                              className="px-3 py-1.5 rounded-lg border border-line text-ink-muted hover:text-ink text-xs font-bold cursor-pointer"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setConfirmingId(product.id)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 text-xs font-bold cursor-pointer"
                          >
                            <span aria-hidden="true" className="material-symbols-outlined">
                              autorenew
                            </span>
                            Renew · {summary.renewal_points} pts
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!loading && rowCount > rows.length && (
            <p className="pt-2 text-[11px] text-ink-muted">
              Showing the first {rows.length} of {rowCount}.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
