"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminProduct, getAdminProducts } from "@/lib/admin-api";
import { formatDate, formatTaka } from "@/lib/admin-format";
import {
  AdminConfirmModal,
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  PRODUCT_STATUS_LABELS,
  PRODUCT_STATUS_OPTIONS,
  ProductAccessNotice,
  canViewAdminProducts,
  getAvailableProductActions,
  useProductStatusAction,
} from "./productGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

export default function AdminProductsPage() {
  return (
    <Suspense fallback={<ProductsPageFallback />}>
      <AdminProductsPageContent />
    </Suspense>
  );
}

function ProductsPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminProductsPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canViewAdminProducts(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  // The backend filters these by primary key (category_id / shop_id). There is
  // no admin endpoint this module is allowed to call to turn them into a
  // labelled dropdown — /api/admin/categories/ needs categories.admin.manage,
  // which a products.view holder does not have — so they are honoured as
  // deep-link scope filters (e.g. from the detail page) and shown as a chip
  // whose label is upgraded from the real rows once they load.
  const urlCategory = searchParams.get("category") ?? "";
  const urlShop = searchParams.get("shop") ?? "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed into the URL (and the
  // actual filter) after a short debounce so we don't fire a request per
  // keystroke. Resynced from the URL during render (not an effect) whenever it
  // changes externally — e.g. browser back/forward or "Clear filters".
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
      if (searchInput !== urlSearch) {
        updateParams({ search: searchInput || null, page: null });
      }
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchProducts = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminProducts(token, {
        search: urlSearch || undefined,
        status: urlStatus || undefined,
        category: urlCategory || undefined,
        shop: urlShop || undefined,
        page: urlPage,
      });
      setProducts(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setProducts([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load products."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlStatus, urlCategory, urlShop, urlPage]);

  useEffect(() => {
    if (!canView) return;
    fetchProducts();
  }, [canView, fetchProducts]);

  const isFiltered = Boolean(urlSearch || urlStatus || urlCategory || urlShop);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, status: null, category: null, shop: null, page: null });
  }, [updateParams]);

  // The backend filtered by this exact id, so every returned row carries the
  // real name for it — a truthful label with no extra request.
  const scopeChips = useMemo(() => {
    const chips: Array<{ key: string; label: string; onRemove: () => void }> = [];
    if (urlShop) {
      chips.push({
        key: "shop",
        label: `Shop: ${products[0]?.shop_name ?? `#${urlShop}`}`,
        onRemove: () => updateParams({ shop: null, page: null }),
      });
    }
    if (urlCategory) {
      chips.push({
        key: "category",
        label: `Category: ${products[0]?.category_name ?? `#${urlCategory}`}`,
        onRemove: () => updateParams({ category: null, page: null }),
      });
    }
    return chips;
  }, [urlShop, urlCategory, products, updateParams]);

  const handleActionSuccess = useCallback((updated: AdminProduct) => {
    setProducts((prev) => prev.map((product) => (product.id === updated.id ? updated : product)));
  }, []);
  const { pendingAction, targetProduct, submitError, requestAction, cancel, confirm } =
    useProductStatusAction(handleActionSuccess);

  const columns: AdminTableColumn<AdminProduct>[] = useMemo(
    () => [
      {
        key: "product",
        header: "Product",
        render: (product) => (
          <Link
            href={`/admin/products/${product.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
          >
            <span className="block line-clamp-1">{product.name}</span>
            <span className="block text-[11px] font-medium text-ink-muted line-clamp-1 font-mono">
              {product.slug}
            </span>
          </Link>
        ),
        width: "w-64",
      },
      {
        key: "shop",
        header: "Shop / Seller",
        render: (product) => (
          <>
            <span className="block line-clamp-1">{product.shop_name ?? "—"}</span>
            <span className="block text-[11px] text-ink-muted line-clamp-1">
              {product.seller_business_name ?? "—"}
            </span>
          </>
        ),
        hideOnMobile: true,
      },
      {
        key: "category",
        header: "Category",
        render: (product) => product.category_name ?? "—",
        hideOnMobile: true,
      },
      {
        key: "price",
        header: "Price",
        render: (product) => formatTaka(product.price),
        align: "right",
        hideOnMobile: true,
        width: "w-28",
      },
      {
        key: "stock",
        header: "Stock",
        render: (product) => (
          <span className={product.stock === 0 ? "text-red-600 font-bold" : undefined}>
            {product.stock}
          </span>
        ),
        align: "right",
        hideOnMobile: true,
        width: "w-20",
      },
      {
        key: "status",
        header: "Status",
        render: (product) => (
          <div className="flex flex-col items-start gap-1">
            <AdminStatusBadge
              status={product.status}
              label={PRODUCT_STATUS_LABELS[product.status]}
            />
            {/* Product.is_publicly_visible: the full public-catalog predicate,
                which also accounts for the category, shop and seller states. */}
            {product.is_publicly_visible && (
              <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wide">
                Live
              </span>
            )}
          </div>
        ),
      },
      {
        key: "created",
        header: "Created",
        render: (product) => formatDate(product.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminProduct>[] = useMemo(() => {
    const definitions = [
      { key: "approve", label: "Approve", icon: "verified", tone: "primary" as const },
      { key: "reject", label: "Reject", icon: "cancel", tone: "danger" as const },
      { key: "publish", label: "Publish", icon: "public", tone: "primary" as const },
      { key: "unpublish", label: "Unpublish", icon: "visibility_off", tone: "danger" as const },
    ];
    return definitions.map(({ key, label, icon, tone }) => ({
      key,
      label,
      icon,
      tone,
      onClick: (product: AdminProduct) => {
        const descriptor = getAvailableProductActions(product, user).find((a) => a.action === key);
        if (descriptor) requestAction(product, descriptor);
      },
      isHidden: (product: AdminProduct) =>
        !getAvailableProductActions(product, user).some((a) => a.action === key),
    }));
  }, [user, requestAction]);

  if (!canView) {
    return <ProductAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Products</h1>
          <p className="text-xs text-ink-muted">
            Moderate catalog listings across every shop — review submissions, approve or reject
            them, and control what is published to the public storefront.
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
              {totalCount.toLocaleString("en-US")} product{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by product name, slug, or shop…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-80"
        />
        <AdminSelectField
          label="Status"
          value={urlStatus}
          options={PRODUCT_STATUS_OPTIONS}
          onChange={(value) => updateParams({ status: value || null, page: null })}
        />
      </AdminFilterBar>

      {scopeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">
            Scoped to
          </span>
          {scopeChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={chip.onRemove}
              className="inline-flex items-center gap-1.5 pl-2.5 pr-2 py-1 rounded-full border border-line bg-surface text-[11px] font-bold text-ink hover:bg-surface-alt transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span className="line-clamp-1 max-w-[16rem]">{chip.label}</span>
              <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                close
              </span>
              <span className="sr-only">Remove this filter</span>
            </button>
          ))}
        </div>
      )}

      <AdminDataTable<AdminProduct>
        caption="Platform product catalog"
        columns={columns}
        rows={products}
        getRowId={(product) => product.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchProducts}
        emptyTitle="No products found"
        emptyMessage={
          isFiltered
            ? "No products match the current filters."
            : "No products have been created on the platform yet."
        }
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
        actions={actions}
        page={urlPage}
        pageSize={PAGE_SIZE}
        totalCount={totalCount}
        onPageChange={(page) => updateParams({ page: page === 1 ? null : String(page) })}
      />

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
