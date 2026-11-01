"use client";

import React, { useId, useState } from "react";
import Dialog from "@/components/feedback/Dialog";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  sellPointsToOnboardedSeller,
  type AdminOnboardingSeller,
  type AdminPointSaleResult,
} from "@/lib/admin-api";
import { formatCount } from "@/lib/admin-format";
import { quickAmounts, saleAmountError } from "./pointSale";

interface SellPointsDialogProps {
  seller: AdminOnboardingSeller;
  /** SellerPointPolicy.minimum_purchase. */
  minimum: number;
  /** The caller's wallet balance. */
  available: number;
  onClose: () => void;
  onSold: (result: AdminPointSaleResult) => void;
  /** The server said the wallet holds a different amount. */
  onBalance: (points: number) => void;
}

/**
 * Sells points from the caller's wallet to one of their approved sellers,
 * after the seller paid them in cash or bKash. Mount it with a `key` per
 * seller, so each sale starts from an empty amount.
 */
export default function SellPointsDialog({
  seller,
  minimum,
  available,
  onClose,
  onSold,
  onBalance,
}: SellPointsDialogProps) {
  const [amount, setAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const inputId = useId();

  const amountError = saleAmountError(amount, minimum, available);
  const parsed = Number(amount);

  const sell = (event: React.FormEvent) => {
    event.preventDefault();
    const token = getAuthToken();
    if (!token || amountError || submitting) return;
    setSubmitting(true);
    setServerError(null);
    sellPointsToOnboardedSeller(token, seller.id, parsed)
      .then(onSold)
      .catch((err: unknown) => {
        const data = err instanceof AdminApiError ? (err.data as { available_points?: unknown } | undefined) : undefined;
        if (typeof data?.available_points === "number") onBalance(data.available_points);
        setServerError(err instanceof Error ? err.message : "The points could not be sold.");
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <Dialog
      open
      onClose={onClose}
      dismissible={!submitting}
      labelledBy={titleId}
      describedBy={descriptionId}
      placement="sheet"
      zIndexClass="z-[100]"
      className="w-full sm:max-w-md bg-surface border border-line rounded-t-2xl sm:rounded-2xl shadow-lg p-6"
    >
      <form onSubmit={sell} className="space-y-4">
        <div>
          <h2 id={titleId} className="text-sm font-extrabold text-ink tracking-tight">
            Sell points to {seller.business_name}
          </h2>
          <p id={descriptionId} className="text-xs text-ink-muted leading-relaxed mt-1.5">
            Take the payment first, in cash or bKash. The points move from your wallet to the seller&apos;s at once,
            and you cannot take them back here.
          </p>
        </div>

        <div>
          <label htmlFor={inputId} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
            Points
          </label>
          <input
            id={inputId}
            type="number"
            inputMode="numeric"
            min={minimum}
            max={available}
            step={1}
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              setServerError(null);
            }}
            disabled={submitting}
            className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
          {quickAmounts(minimum, available).length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2" role="group" aria-label="Quick amounts">
              {quickAmounts(minimum, available).map((quick) => (
                <button
                  key={quick}
                  type="button"
                  onClick={() => {
                    setAmount(String(quick));
                    setServerError(null);
                  }}
                  disabled={submitting}
                  className="px-2.5 py-1 rounded-full border border-line text-[11px] font-bold text-ink-muted hover:text-ink hover:border-primary/40 cursor-pointer disabled:opacity-50"
                >
                  {formatCount(quick)}
                </button>
              ))}
            </div>
          )}
          <p className={`text-[11px] mt-2 ${amount && amountError ? "text-danger" : "text-ink-muted"}`}>
            {amount && amountError
              ? amountError
              : amountError
              ? `At least ${formatCount(minimum)}; your wallet holds ${formatCount(available)}.`
              : `Your wallet: ${formatCount(available)} → ${formatCount(available - parsed)} points.`}
          </p>
        </div>

        {serverError && (
          <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
            {serverError}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={Boolean(amountError) || submitting}
            className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Selling..." : amountError ? "Sell points" : `Sell ${formatCount(parsed)} points`}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
