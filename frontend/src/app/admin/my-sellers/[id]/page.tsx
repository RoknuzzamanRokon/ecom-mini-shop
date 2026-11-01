"use client";

import React, { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { formatImageUrl } from "@/lib/api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  AdminApiError,
  getMyOnboardedProduct,
  getMyOnboardedSeller,
  updateMyOnboardedProduct,
  updateMyOnboardedSeller,
  updateMyOnboardedShop,
  type AdminEditSession,
  type AdminMyOnboardedSeller,
  type AdminOnboardedProductChanges,
  type AdminOnboardedProductDetail,
  type AdminOnboardedSellerChanges,
  type AdminOnboardedShopChanges,
  type AdminOnboardingShop,
} from "@/lib/admin-api";
import { formatCount, formatDateTime, formatTaka } from "@/lib/admin-format";
import { formatBangladeshiMobile } from "@/lib/phone";
import { AdminStatusBadge } from "@/components/admin/shared";
import { SELLER_STATUS_LABELS, SELLER_TYPE_LABELS } from "../../sellers/sellerGovernance";
import EditDialog from "../EditDialog";
import EditSessionPanel from "../EditSessionPanel";
import { productForm, sellerForm, shopForm, type EditForm } from "../editForms";
import { liveState } from "../editSession";

/** OnboardingService's EDITABLE_SELLER_STATUSES: awaiting approval or live. */
const EDITABLE_STATUSES = new Set(["PENDING", "UNDER_REVIEW", "APPROVED", "ACTIVE"]);

const EDIT_BUTTON =
  "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-line text-[11px] font-bold uppercase tracking-wide text-ink hover:bg-surface-alt cursor-pointer disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

type Editing =
  | { kind: "seller" }
  | { kind: "shop"; shop: AdminOnboardingShop }
  | { kind: "product"; product: AdminOnboardedProductDetail };

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-36 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value || "—"}</dd>
    </div>
  );
}

function EditButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" className={EDIT_BUTTON} onClick={onClick} disabled={disabled} aria-label={label}>
      <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
        edit
      </span>
      Edit
    </button>
  );
}

/**
 * One seller the Sales Team member onboarded: details, shops, the products
 * they added, and corrections inside an edit session the seller consents to
 * with a code (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §1, §3).
 */
export default function AdminMySellerDetailPage() {
  const params = useParams<{ id: string }>();
  const sellerId = params.id;
  const { user } = useAuth();
  const canUse = hasAnyPermission(user, ADMIN_PERMISSIONS.sellersOnboard);

  const [seller, setSeller] = useState<AdminMyOnboardedSeller | null>(null);
  const [session, setSession] = useState<AdminEditSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // State is only set in the promise callbacks.
  const fetchSeller = useCallback((): Promise<void> => {
    const token = getAuthToken();
    if (!token) {
      return Promise.resolve().then(() => {
        setLoading(false);
        setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      });
    }
    return getMyOnboardedSeller(token, sellerId)
      .then((data) => {
        setSeller(data);
        setSession(data.edit_session);
        setError(null);
      })
      .catch((err: unknown) => {
        setSeller(null);
        setError(err instanceof Error ? err : new Error("Failed to load the seller."));
      })
      .finally(() => setLoading(false));
  }, [sellerId]);

  useEffect(() => {
    if (!canUse) return;
    fetchSeller();
  }, [canUse, fetchSeller]);

  // Tick while a code waits or editing is open, so the countdown moves and the
  // Edit buttons go away when the window closes.
  const ticking = session?.state === "open" || session?.state === "waiting";
  useEffect(() => {
    if (!ticking) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);

  const handleSession = useCallback((next: AdminEditSession) => {
    setNow(Date.now());
    setSession(next);
  }, []);

  const sessionEnded = useCallback(() => {
    setSession((current) => (current ? { ...current, state: "ended" } : current));
  }, []);

  const openProduct = (productId: number) => {
    const token = getAuthToken();
    if (!token) return;
    setOpening(productId);
    setNotice(null);
    getMyOnboardedProduct(token, productId)
      .then((product) => setEditing({ kind: "product", product }))
      .catch((err: unknown) => setNotice(err instanceof Error ? err.message : "The product could not be loaded."))
      .finally(() => setOpening(null));
  };

  const backLink = (
    <Link
      href="/admin/my-sellers"
      className="inline-flex items-center gap-1 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
        arrow_back
      </span>
      Back to My Sellers
    </Link>
  );

  if (!canUse) {
    return (
      <div className="space-y-6">
        {backLink}
        <p className="text-xs text-ink-muted">
          This page is for the Sales Team: it needs <code className="font-mono text-[11px]">sellers.onboard</code>.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading seller">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
          <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
          <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
        </div>
      </div>
    );
  }

  if (error || !seller) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <p className="text-sm font-bold text-ink">{isNotFound ? "Seller not found" : "Unable to load the seller"}</p>
          <p className="text-xs text-ink-muted max-w-md">
            {isNotFound ? "You did not onboard a seller with this id." : error?.message || "An unexpected error occurred."}
          </p>
          {!isNotFound && (
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                fetchSeller();
              }}
              className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider cursor-pointer"
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  const editable = EDITABLE_STATUSES.has(seller.status);
  const canEdit = editable && liveState(session, now) === "open";
  const fullName = [seller.first_name, seller.last_name].filter(Boolean).join(" ");

  let form: (EditForm & { title: string; description: string; save: (changes: object) => Promise<unknown> }) | null =
    null;
  const token = getAuthToken() ?? "";
  if (editing?.kind === "seller") {
    form = {
      ...sellerForm(seller),
      title: `Edit ${seller.business_name}`,
      description: "The business details. The seller changes their own login details.",
      save: (changes) =>
        updateMyOnboardedSeller(token, seller.id, changes as AdminOnboardedSellerChanges).then((updated) => {
          setSeller(updated);
          setNotice("The business details were saved.");
        }),
    };
  } else if (editing?.kind === "shop") {
    const shop = editing.shop;
    form = {
      ...shopForm(shop),
      title: `Edit ${shop.name}`,
      description: "The shop's profile, phones and location.",
      save: (changes) =>
        updateMyOnboardedShop(token, shop.id, changes as AdminOnboardedShopChanges).then((updated) => {
          setSeller((current) =>
            current ? { ...current, shops: current.shops.map((s) => (s.id === updated.id ? updated : s)) } : current
          );
          setNotice(`${updated.name} was saved.`);
        }),
    };
  } else if (editing?.kind === "product") {
    const product = editing.product;
    form = {
      ...productForm(product),
      title: `Edit ${product.name}`,
      description: "The same changes the seller could make. A live product stays live.",
      save: (changes) =>
        updateMyOnboardedProduct(token, product.id, changes as AdminOnboardedProductChanges).then((updated) => {
          setSeller((current) =>
            current
              ? {
                  ...current,
                  shops: current.shops.map((s) => ({
                    ...s,
                    products: s.products.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)),
                  })),
                }
              : current
          );
          setNotice(`${updated.name} was saved.`);
        }),
    };
  }

  return (
    <div className="space-y-6">
      {backLink}

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h1 className="text-xl font-black text-ink tracking-tight break-words">{seller.business_name}</h1>
          <AdminStatusBadge status={seller.status} label={SELLER_STATUS_LABELS[seller.status]} />
        </div>
        <p className="text-xs text-ink-muted mt-1">
          @{seller.username} · {SELLER_TYPE_LABELS[seller.seller_type] ?? seller.seller_type} · opened{" "}
          {formatDateTime(seller.created_at)}
        </p>
        {seller.rejection_reason && <p className="text-xs text-danger mt-3">Rejected: {seller.rejection_reason}</p>}
      </div>

      <EditSessionPanel
        sellerId={seller.id}
        businessName={seller.business_name}
        session={session}
        now={now}
        onSession={handleSession}
        editable={editable}
      />

      {notice && (
        <div role="status" className="rounded-xl border border-success/30 bg-success/10 p-3 text-xs font-semibold text-success">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">Business</h2>
            {canEdit && <EditButton label="Edit business details" onClick={() => setEditing({ kind: "seller" })} />}
          </div>
          <dl>
            <InfoRow label="Business phone" value={seller.business_phone} />
            <InfoRow label="Business email" value={seller.business_email} />
            <InfoRow label="Tax ID" value={seller.tax_id} />
            <InfoRow label="Description" value={seller.description} />
          </dl>
        </section>
        <section className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">Account</h2>
          <dl>
            <InfoRow label="Username" value={`@${seller.username}`} />
            <InfoRow label="Name" value={fullName} />
            <InfoRow label="Mobile (sign-in)" value={seller.phone && formatBangladeshiMobile(seller.phone)} />
            <InfoRow label="Email" value={seller.email} />
          </dl>
        </section>
        <section className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">Points</h2>
          <dl>
            <InfoRow label="Starting points" value={formatCount(seller.starting_points)} />
            <InfoRow label="Points left" value={formatCount(seller.points_balance)} />
            <InfoRow label="Tokens earned" value={formatCount(seller.tokens_awarded)} />
          </dl>
        </section>
      </div>

      <div className="space-y-4">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
          Shops ({formatCount(seller.shops.length)})
        </h2>
        {!seller.can_view_products && (
          <p role="note" className="rounded-xl border border-accent/30 bg-accent/10 p-3 text-xs font-medium text-accent">
            You cannot see products: an administrator turned off your permission to view the products you added.
          </p>
        )}
        {seller.shops.length === 0 && <p className="text-xs text-ink-muted">No shop added yet.</p>}
        {seller.shops.map((shop) => (
          <section key={shop.id} aria-label={shop.name} className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-black text-ink break-words">{shop.name}</h3>
                  <AdminStatusBadge status={shop.status} />
                </div>
                <p className="text-xs text-ink-muted mt-1 break-words">
                  {[shop.address, shop.phone, ...shop.additional_phones].filter(Boolean).join(" · ") ||
                    "No address or phone given."}
                </p>
              </div>
              {canEdit && <EditButton label={`Edit ${shop.name}`} onClick={() => setEditing({ kind: "shop", shop })} />}
            </div>
            {seller.can_view_products &&
              (shop.products.length === 0 ? (
                <p className="text-xs text-ink-muted mt-4 pt-4 border-t border-line">No products you added.</p>
              ) : (
                <ul className="mt-4 pt-2 border-t border-line divide-y divide-line">
                  {shop.products.map((product) => (
                    <li key={product.id} className="flex items-center gap-3 py-3">
                      <Image
                        src={formatImageUrl(product.image_url)}
                        alt=""
                        width={48}
                        height={48}
                        className="w-12 h-12 shrink-0 rounded-lg object-cover border border-line bg-surface-alt"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold text-ink break-words">{product.name}</p>
                        <p className="text-[11px] text-ink-muted">
                          {formatTaka(product.price)} · {formatCount(product.stock)} in stock
                        </p>
                      </div>
                      <AdminStatusBadge status={product.status} />
                      {canEdit && (
                        <EditButton
                          label={`Edit ${product.name}`}
                          onClick={() => openProduct(product.id)}
                          disabled={opening === product.id}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              ))}
          </section>
        ))}
      </div>

      {form && editing && (
        <EditDialog
          key={editing.kind === "seller" ? "seller" : `${editing.kind}-${editing.kind === "shop" ? editing.shop.id : editing.product.id}`}
          title={form.title}
          description={form.description}
          fields={form.fields}
          initial={form.initial}
          toChanges={form.toChanges}
          onSave={form.save}
          onClose={() => setEditing(null)}
          onSessionEnded={sessionEnded}
        />
      )}
    </div>
  );
}
