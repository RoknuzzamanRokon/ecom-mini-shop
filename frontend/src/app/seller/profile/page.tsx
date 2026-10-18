"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSeller } from "@/components/seller/SellerGuard";
import { getSellerPointHistory, getSellerWallet, updateSellerProfile } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { formatCount, formatDate } from "@/lib/admin-format";
import type { PointTransaction, SellerWallet } from "@/lib/types";
import PointsBalanceTile, {
  POINTS_TILE_HEADER_LINK,
  POINTS_TILE_PRIMARY_ACTION,
  POINTS_TILE_SECONDARY_ACTION,
} from "@/components/points/PointsBalanceTile";
import PointMovementList, { type PointMovementRow } from "@/components/points/PointMovementList";

const CARD = "bg-surface rounded-2xl border border-line shadow-xs";
const CARD_TITLE = "text-sm font-extrabold text-ink uppercase tracking-wider";
const INPUT =
  "w-full min-h-10 px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-sm placeholder:text-ink-faint focus:outline-none focus:border-primary focus-visible:ring-2 focus-visible:ring-focus/40";
const LABEL = "block text-xs font-semibold text-ink mb-1.5";
const REQUEST_POINTS_HREF = "/seller/support/new?category=POINTS";
const RECENT_MOVEMENTS = 4;

// Material Symbols ignores Tailwind's text-[Npx] (the Google Fonts stylesheet
// wins the cascade), so a glyph that must sit below 24px is sized inline.
const ICON_16 = { fontSize: 16 } as const;
const ICON_18 = { fontSize: 18 } as const;

const MOVEMENT_ICONS: Record<string, string> = {
  PRODUCT_CREATION: "inventory_2",
  ADMIN_CREDIT: "add_card",
  ADMIN_DEBIT: "remove_circle",
  BONUS: "redeem",
  REFUND: "undo",
  ADJUSTMENT: "tune",
};

function toMovementRow(txn: PointTransaction): PointMovementRow {
  return {
    id: txn.id,
    icon: MOVEMENT_ICONS[txn.transaction_type] ?? "toll",
    title: txn.transaction_type_display,
    reason: txn.reason,
    amount: txn.amount,
    // `amount` is always positive; the direction lives in the balances.
    incoming: txn.balance_after >= txn.balance_before,
    balanceAfter: txn.balance_after,
    when: txn.created_at,
  };
}

export default function SellerProfilePage() {
  const { seller, refreshDashboard } = useSeller();

  const [formData, setFormData] = useState({
    business_name: "",
    business_email: "",
    business_phone: "",
    tax_id: "",
    description: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [wallet, setWallet] = useState<SellerWallet | null>(null);
  const [history, setHistory] = useState<PointTransaction[]>([]);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<string | null>(null);

  useEffect(() => {
    if (seller) {
      setFormData({
        business_name: seller.business_name || "",
        business_email: seller.business_email || "",
        business_phone: seller.business_phone || "",
        tax_id: seller.tax_id || "",
        description: seller.description || "",
      });
    }
  }, [seller]);

  // State is only set in the promise callbacks, so the effect below never
  // updates state synchronously; a retry flips the loading flag itself first.
  const fetchWallet = useCallback(() => {
    const token = getAuthToken() ?? "";
    return Promise.all([getSellerWallet(token), getSellerPointHistory(token)])
      .then(([walletRes, historyRes]) => {
        setWallet(walletRes);
        setHistory(historyRes);
        setWalletError(null);
      })
      .catch((err: unknown) => {
        setWalletError(err instanceof Error ? err.message : "The request failed.");
      })
      .finally(() => setWalletLoading(false));
  }, []);

  const retryWallet = useCallback(() => {
    setWalletLoading(true);
    setWalletError(null);
    fetchWallet();
  }, [fetchWallet]);

  useEffect(() => {
    fetchWallet();
  }, [fetchWallet]);

  const movements = useMemo(
    () => history.slice(0, RECENT_MOVEMENTS).map(toMovementRow),
    [history]
  );

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();

    if (!token) return;

    setSubmitting(true);
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      await updateSellerProfile(token, formData);
      setSuccessMsg("Seller profile updated successfully.");
      await refreshDashboard();
    } catch (err: unknown) {
      setErrorMsg((err instanceof Error && err.message) || "Failed to update seller profile.");
    } finally {
      setSubmitting(false);
    }
  };

  const businessName = seller?.business_name || "Your business";
  const initial = (businessName[0] || "S").toUpperCase();
  const operational = Boolean(seller?.is_operational);

  const balance = wallet?.balance ?? null;
  const cost = wallet?.product_creation_cost ?? 0;
  const shortfall = wallet && cost > 0 && wallet.balance < cost ? cost - wallet.balance : 0;

  // Every listing costs at least 1 point (ProductCreationCost), so cost > 0 here.
  let tileCaption: React.ReactNode = "Points pay for new product listings.";
  const nextExpiry = wallet?.upcoming_expiries[0];
  if (wallet && cost > 0 && !shortfall) {
    const listings = Math.floor(wallet.balance / cost);
    tileCaption = (
      <>
        Enough for <strong className="text-nav-active-text">{formatCount(listings)}</strong> new{" "}
        {listings === 1 ? "listing" : "listings"} at {formatCount(cost)} pts each.
        {nextExpiry && (
          <>
            {" "}
            {formatCount(nextExpiry.points)} pts expire on{" "}
            {new Date(nextExpiry.expires_at).toLocaleDateString()}.
          </>
        )}
      </>
    );
  }

  return (
    <div className="space-y-6">
      {/* Hero: the business, beside its points */}
      <section aria-labelledby="seller-name" className={`${CARD} p-5 sm:p-6`}>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
          <div className="flex flex-col justify-center gap-4 min-w-0">
            <div className="flex flex-col sm:flex-row sm:items-start gap-4 min-w-0">
              <div
                aria-hidden="true"
                className="w-20 h-20 shrink-0 rounded-2xl bg-primary/10 text-primary flex items-center justify-center font-black text-3xl border border-primary/20"
              >
                {initial}
              </div>
              <div className="min-w-0">
                <ul aria-label="Seller status" className="flex flex-wrap gap-1.5">
                  <li
                    className={`inline-flex items-center gap-1.5 min-h-7 px-2.5 rounded-full text-[11px] font-extrabold border ${
                      operational
                        ? "bg-success/10 text-success border-success/25"
                        : "bg-accent/15 text-accent border-accent/25"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`w-2 h-2 rounded-full ${operational ? "bg-success" : "bg-accent"}`}
                    />
                    {operational ? "Operational" : seller?.status_display || "Not operational"}
                  </li>
                  {operational && seller?.status_display && (
                    <li className="inline-flex items-center min-h-7 px-2.5 rounded-full text-[11px] font-extrabold bg-surface-alt text-ink-body border border-line">
                      {seller.status_display}
                    </li>
                  )}
                  {(seller?.seller_type_display || seller?.seller_type) && (
                    <li className="inline-flex items-center min-h-7 px-2.5 rounded-full text-[11px] font-extrabold bg-primary/10 text-primary border border-primary/20">
                      {seller?.seller_type_display || seller?.seller_type}
                    </li>
                  )}
                </ul>
                <h1
                  id="seller-name"
                  className="mt-2.5 text-2xl sm:text-3xl font-black text-ink tracking-tight break-words"
                >
                  <span className="sr-only">Seller profile: </span>
                  {businessName}
                </h1>
                <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-muted">
                  {seller?.username && <MetaItem icon="alternate_email">{seller.username}</MetaItem>}
                  {(seller?.business_email || seller?.user_email) && (
                    <MetaItem icon="mail">{seller?.business_email || seller?.user_email}</MetaItem>
                  )}
                  {seller?.business_phone && <MetaItem icon="call">{seller.business_phone}</MetaItem>}
                  {seller?.created_at && (
                    <MetaItem icon="calendar_month">Seller since {formatDate(seller.created_at)}</MetaItem>
                  )}
                </ul>
              </div>
            </div>

            {seller?.description && (
              <p className="text-xs text-ink-body leading-relaxed max-w-prose line-clamp-3 sm:pl-24">
                {seller.description}
              </p>
            )}
          </div>

          <PointsBalanceTile
            balance={balance}
            loading={walletLoading && !wallet}
            error={walletError}
            onRetry={retryWallet}
            caption={tileCaption}
            headerAction={
              <Link href="/seller/wallet" className={POINTS_TILE_HEADER_LINK}>
                Wallet
                <span aria-hidden="true" className="material-symbols-outlined" style={ICON_16}>
                  arrow_forward
                </span>
              </Link>
            }
          >
            {shortfall > 0 && (
              <p className="flex items-start gap-2 rounded-lg bg-accent/15 border border-accent/30 px-3 py-2 text-xs text-nav-active-text">
                <span aria-hidden="true" className="material-symbols-outlined text-accent shrink-0" style={ICON_18}>
                  warning
                </span>
                <span>
                  You need <strong>{formatCount(shortfall)}</strong> more{" "}
                  {shortfall === 1 ? "point" : "points"} to list a product ({formatCount(cost)} each).
                </span>
              </p>
            )}
            {!walletError && (
              <div className="flex flex-wrap gap-2 mt-1">
                <Link
                  href={REQUEST_POINTS_HREF}
                  className={shortfall > 0 ? POINTS_TILE_PRIMARY_ACTION : POINTS_TILE_SECONDARY_ACTION}
                >
                  <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
                    add_card
                  </span>
                  Request points
                </Link>
              </div>
            )}
          </PointsBalanceTile>
        </div>
      </section>

      {seller?.rejection_reason && (
        <Notice icon="gpp_bad" title="Rejection notice">
          {seller.rejection_reason}
        </Notice>
      )}
      {seller?.suspension_reason && (
        <Notice icon="block" title="Suspension notice">
          {seller.suspension_reason}
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] items-start">
        {/* Editable business information */}
        <section aria-labelledby="business-title" className={`${CARD} p-5 sm:p-6`}>
          <h2 id="business-title" className={CARD_TITLE}>
            Business contact &amp; public information
          </h2>
          <p className="text-xs text-ink-muted mt-1 mb-5">
            Buyers see these details on your shop pages.
          </p>

          <div aria-live="polite">
            {successMsg && (
              <div
                role="status"
                className="mb-4 p-3.5 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-semibold flex items-center gap-2"
              >
                <span aria-hidden="true" className="material-symbols-outlined">
                  check_circle
                </span>
                <span>{successMsg}</span>
              </div>
            )}
          </div>
          {errorMsg && (
            <div
              role="alert"
              className="mb-4 p-3.5 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2"
            >
              <span aria-hidden="true" className="material-symbols-outlined">
                error
              </span>
              <span>{errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="business_name" className={LABEL}>
                Business name <span className="text-accent" aria-hidden="true">*</span>
              </label>
              <input
                id="business_name"
                type="text"
                name="business_name"
                required
                value={formData.business_name}
                onChange={handleChange}
                placeholder="e.g. Apex Tech Store"
                className={INPUT}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="business_email" className={LABEL}>
                  Business email
                </label>
                <input
                  id="business_email"
                  type="email"
                  name="business_email"
                  autoComplete="email"
                  value={formData.business_email}
                  onChange={handleChange}
                  placeholder="contact@business.com"
                  className={INPUT}
                />
              </div>
              <div>
                <label htmlFor="business_phone" className={LABEL}>
                  Business phone
                </label>
                <input
                  id="business_phone"
                  type="tel"
                  name="business_phone"
                  autoComplete="tel"
                  value={formData.business_phone}
                  onChange={handleChange}
                  placeholder="+880 1712 345678"
                  className={INPUT}
                />
              </div>
            </div>

            <div>
              <label htmlFor="tax_id" className={LABEL}>
                Tax ID / trade licence number
              </label>
              <input
                id="tax_id"
                type="text"
                name="tax_id"
                value={formData.tax_id}
                onChange={handleChange}
                placeholder="e.g. TRAD-123456"
                className={INPUT}
              />
            </div>

            <div>
              <label htmlFor="description" className={LABEL}>
                Business description
              </label>
              <textarea
                id="description"
                name="description"
                rows={4}
                value={formData.description}
                onChange={handleChange}
                placeholder="Describe your business and catalog..."
                className={INPUT}
              />
            </div>

            <div className="flex justify-end pt-4 border-t border-line">
              <button
                type="submit"
                disabled={submitting}
                className="min-h-10 px-5 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-colors flex items-center gap-2 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {submitting ? (
                  <>
                    <span aria-hidden="true" className="material-symbols-outlined animate-spin" style={ICON_18}>
                      progress_activity
                    </span>
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <span aria-hidden="true" className="material-symbols-outlined" style={ICON_18}>
                      save
                    </span>
                    <span>Save changes</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </section>

        <div className="space-y-6 min-w-0">
          {/* Points activity */}
          <section aria-labelledby="points-title" className={`${CARD} p-5 sm:p-6`}>
            <div className="flex items-start justify-between gap-3">
              <h2 id="points-title" className={CARD_TITLE}>
                Points activity
              </h2>
              <Link
                href="/seller/wallet"
                className="inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Full history
                <span aria-hidden="true" className="material-symbols-outlined" style={ICON_16}>
                  arrow_forward
                </span>
              </Link>
            </div>

            <dl className="grid grid-cols-2 gap-3 mt-4">
              <Figure
                label="Credited"
                value={wallet?.total_earned}
                tone="text-success"
                loading={walletLoading && !wallet}
              />
              <Figure
                label="Spent"
                value={wallet?.total_spent}
                tone="text-ink"
                loading={walletLoading && !wallet}
              />
            </dl>

            <div className="mt-5">
              {walletLoading && !wallet ? (
                <div className="space-y-3" aria-hidden="true">
                  {[0, 1, 2].map((key) => (
                    <div key={key} className="h-12 rounded-xl bg-surface-alt animate-pulse" />
                  ))}
                </div>
              ) : walletError ? (
                <p className="text-xs text-ink-muted">Movements appear here once your points load.</p>
              ) : movements.length === 0 ? (
                <div className="flex items-start gap-3 rounded-xl border border-dashed border-line bg-surface-alt/40 p-4">
                  <span
                    aria-hidden="true"
                    className="material-symbols-outlined w-10 h-10 shrink-0 rounded-xl bg-accent/15 text-accent flex items-center justify-center"
                  >
                    savings
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-ink">No point movements yet</p>
                    <p className="text-[11px] text-ink-muted mt-0.5 leading-relaxed">
                      Points MiniShop gives you, and the points each new listing uses, show up here.
                    </p>
                  </div>
                </div>
              ) : (
                <PointMovementList rows={movements} label="Recent point movements" />
              )}
            </div>
          </section>

          {/* Registration details */}
          <section aria-labelledby="registration-title" className={`${CARD} p-5 sm:p-6`}>
            <h2 id="registration-title" className={`${CARD_TITLE} mb-3`}>
              Platform registration
            </h2>
            <dl>
              <InfoRow label="Account type" value={seller?.seller_type_display || seller?.seller_type} />
              <InfoRow label="Status" value={seller?.status_display || seller?.status} />
              <InfoRow
                label="Selling"
                value={operational ? "Active and allowed to sell" : "Suspended or not yet operational"}
              />
              <InfoRow label="User account" value={seller?.username} />
              <InfoRow label="Account email" value={seller?.user_email} />
              <InfoRow label="Approved" value={seller?.approved_at ? formatDate(seller.approved_at) : null} />
            </dl>
          </section>
        </div>
      </div>
    </div>
  );
}

function MetaItem({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <li className="inline-flex items-center gap-1.5 min-w-0 break-all">
      <span aria-hidden="true" className="material-symbols-outlined text-ink-faint" style={ICON_16}>
        {icon}
      </span>
      {children}
    </li>
  );
}

function Notice({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent/10 px-4 py-3 text-xs"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-accent shrink-0">
        {icon}
      </span>
      <p className="text-ink-body min-w-0">
        <strong className="text-ink">{title}:</strong> {children}
      </p>
    </div>
  );
}

function Figure({
  label,
  value,
  tone,
  loading,
}: {
  label: string;
  value: number | undefined;
  tone: string;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface-alt/60 border border-line-subtle px-4 py-3 flex flex-col-reverse">
      <dt className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">{label}</dt>
      <dd className={`text-xl font-black tabular-nums leading-tight ${tone}`}>
        {loading ? (
          <span className="block h-6 w-14 rounded-md bg-surface-sunken animate-pulse" />
        ) : (
          <>
            {value === undefined ? "—" : formatCount(value)}
            <span className="text-xs font-bold text-ink-muted ml-1">pts</span>
          </>
        )}
      </dd>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line-subtle last:border-0 text-xs">
      <dt className="sm:w-28 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className={`min-w-0 break-words ${empty ? "text-ink-faint" : "text-ink font-medium"}`}>
        {empty ? "Not set" : value}
      </dd>
    </div>
  );
}
