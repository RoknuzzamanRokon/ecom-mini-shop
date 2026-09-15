"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminProduct, getAdminProductDetail } from "@/lib/admin-api";
import { formatDateTime, formatTaka } from "@/lib/admin-format";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  PRODUCT_STATUS_LABELS,
  ProductAccessNotice,
  canViewAdminProducts,
  getAvailableProductActions,
  useProductStatusAction,
} from "../productGovernance";

const ACTION_BUTTON_TONE: Record<string, string> = {
  primary: "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
  danger: "bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600",
  default: "border border-line text-ink hover:bg-surface-alt focus-visible:outline-primary",
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-40 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value}</dd>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading product detail">
      <div className="h-6 w-40 bg-surface-alt animate-pulse rounded-md" />
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[0, 1].map((i) => (
          <div key={i} className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
            <div className="h-4 w-32 bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-full bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-3/4 bg-surface-alt animate-pulse rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminProductDetailPage() {
  const params = useParams<{ id: string }>();
  const productId = params.id;
  const { user } = useAuth();

  const canView = canViewAdminProducts(user);

  const [product, setProduct] = useState<AdminProduct | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchProduct = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminProductDetail(token, productId);
      setProduct(data);
    } catch (err) {
      setProduct(null);
      setError(err instanceof Error ? err : new Error("Failed to load product."));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    if (!canView) return;
    fetchProduct();
  }, [canView, fetchProduct]);

  const handleActionSuccess = useCallback((updated: AdminProduct) => {
    setProduct(updated);
  }, []);
  const { pendingAction, targetProduct, submitError, requestAction, cancel, confirm } =
    useProductStatusAction(handleActionSuccess);

  const backLink = (
    <Link
      href="/admin/products"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Products
    </Link>
  );

  if (!canView) {
    return <ProductAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !product) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              {isNotFound ? "search_off" : "error"}
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">
              {isNotFound ? "Product not found" : "Unable to load product"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This product does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchProduct}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
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

  const availableActions = getAvailableProductActions(product, user);
  const canSeeShops = hasAnyPermission(user, ADMIN_PERMISSIONS.shopsView);
  const discounted =
    product.old_price !== null && Number(product.old_price) > Number(product.price);

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {product.name}
              </h1>
              <AdminStatusBadge
                status={product.status}
                label={PRODUCT_STATUS_LABELS[product.status]}
              />
              {/* Product.is_publicly_visible — the same predicate as
                  ProductQuerySet.public(), so it also reflects the category,
                  shop and seller states that are not in this serializer. */}
              {product.is_publicly_visible ? (
                <AdminStatusBadge status={null} label="Live in catalog" tone="success" />
              ) : (
                <AdminStatusBadge status={null} label="Not in catalog" tone="neutral" />
              )}
              {!product.is_active && (
                <AdminStatusBadge status={null} label="Inactive" tone="warning" />
              )}
            </div>
            <p className="text-xs text-ink-muted mt-1 font-mono">{product.slug}</p>
            <p className="text-[11px] text-ink-muted mt-2">Product ID #{product.id}</p>
          </div>

          {availableActions.length > 0 && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {availableActions.map((descriptor) => (
                <button
                  key={descriptor.action}
                  type="button"
                  onClick={() => requestAction(product, descriptor)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 ${ACTION_BUTTON_TONE[descriptor.tone]}`}
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    {descriptor.icon}
                  </span>
                  {descriptor.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {product.status === "DRAFT" && (
          <p className="text-xs text-ink-muted leading-relaxed mt-4 pt-4 border-t border-line">
            This listing is still a seller draft and has not been submitted for review, so there is
            no moderation decision to make yet.
          </p>
        )}

        {product.rejection_reason && (
          <div className="mt-4 pt-4 border-t border-line">
            <p className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1">
              Rejection Reason
            </p>
            <p className="text-xs text-red-600 leading-relaxed whitespace-pre-line">
              {product.rejection_reason}
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Commercial information */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Commercial
          </h2>
          <dl>
            <InfoRow
              label="Price"
              value={
                <span className="inline-flex items-center gap-2">
                  <span className="font-bold">{formatTaka(product.price)}</span>
                  {discounted && (
                    <span className="text-ink-muted line-through">
                      {formatTaka(product.old_price)}
                    </span>
                  )}
                </span>
              }
            />
            <InfoRow
              label="Stock"
              value={
                product.stock === 0 ? (
                  <span className="text-red-600 font-bold">Out of stock</span>
                ) : (
                  `${product.stock} in stock`
                )
              }
            />
            <InfoRow label="Badge" value={product.badge || "—"} />
            <InfoRow label="Active Flag" value={product.is_active ? "Active" : "Inactive"} />
          </dl>
        </div>

        {/* Ownership */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Ownership
          </h2>
          <dl>
            <InfoRow label="Shop" value={product.shop_name ?? "— (no shop assigned)"} />
            <InfoRow label="Seller" value={product.seller_business_name ?? "—"} />
          </dl>
          {canSeeShops && product.shop_id !== null && (
            <Link
              href={`/admin/shops/${product.shop_id}`}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                storefront
              </span>
              Open shop governance
            </Link>
          )}
        </div>

        {/* Classification */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Classification
          </h2>
          <dl>
            <InfoRow label="Category" value={product.category_name ?? "—"} />
          </dl>
          {product.category_id !== null && (
            <Link
              href={`/admin/products?category=${product.category_id}`}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                category
              </span>
              All products in this category
            </Link>
          )}
        </div>

        {/* Governance metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Governance Metadata
          </h2>
          <dl>
            <InfoRow label="Created" value={formatDateTime(product.created_at)} />
            <InfoRow label="Submitted" value={formatDateTime(product.submitted_at)} />
            <InfoRow label="Reviewed" value={formatDateTime(product.reviewed_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(product.updated_at)} />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            The admin product serializer does not expose the reviewing staff account, so no
            reviewer identity is shown here.
          </p>
        </div>
      </div>

      <AdminConfirmModal
        open={Boolean(pendingAction && targetProduct)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetProduct && pendingAction ? pendingAction.confirmMessage(targetProduct) : ""}
            {submitError && <p className="mt-2 font-semibold text-red-600">{submitError}</p>}
          </>
        }
        confirmLabel={pendingAction?.label ?? "Confirm"}
        destructive={pendingAction?.destructive ?? false}
        requireReason={pendingAction?.requiresReason ?? false}
        reasonRequired={pendingAction?.requiresReason ?? false}
        reasonLabel="Reason"
        reasonPlaceholder="Explain the decision for the seller's record…"
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
