"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminCategory,
  createAdminCategory,
  getAdminCategories,
  updateAdminCategory,
} from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import {
  AdminDataTable,
  AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminStatusBadge,
  type AdminRowAction,
  type AdminTableColumn,
} from "@/components/admin/shared";
import {
  CategoryAccessNotice,
  CategoryForm,
  EMPTY_CATEGORY_FORM,
  canManageAdminCategories,
  formValuesToPayload,
  type CategoryFormValues,
} from "./categoryGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py (the backend's default). */
const PAGE_SIZE = 20;

/** The backend parses "true"/"1" and "false"/"0"; anything else is ignored. */
const ACTIVE_OPTIONS = [
  { value: "true", label: "Active" },
  { value: "false", label: "Inactive" },
];

export default function AdminCategoriesPage() {
  return (
    <Suspense fallback={<CategoriesPageFallback />}>
      <AdminCategoriesPageContent />
    </Suspense>
  );
}

function CategoriesPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminCategoriesPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canManage = canManageAdminCategories(user);

  const urlSearch = searchParams.get("search") ?? "";
  const urlActive = searchParams.get("is_active") ?? "";
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

  const [categories, setCategories] = useState<AdminCategory[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchCategories = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getAdminCategories(token, {
        search: urlSearch || undefined,
        is_active: urlActive === "" ? undefined : urlActive === "true",
        page: urlPage,
      });
      setCategories(data.results);
      setTotalCount(data.count);
    } catch (err) {
      setCategories([]);
      setTotalCount(0);
      setError(err instanceof Error ? err : new Error("Failed to load categories."));
    } finally {
      setLoading(false);
    }
  }, [urlSearch, urlActive, urlPage]);

  useEffect(() => {
    if (!canManage) return;
    fetchCategories();
  }, [canManage, fetchCategories]);

  const isFiltered = Boolean(urlSearch || urlActive);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, is_active: null, page: null });
  }, [updateParams]);

  // --- Create -------------------------------------------------------------
  const [createOpen, setCreateOpen] = useState(false);
  const [createValues, setCreateValues] = useState<CategoryFormValues>(EMPTY_CATEGORY_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const closeCreate = useCallback(() => {
    setCreateOpen(false);
    setCreateValues(EMPTY_CATEGORY_FORM);
    setCreateError(null);
  }, []);

  const submitCreate = useCallback(async () => {
    // `creating` also drives the form's disabled state, so a second submit
    // cannot be started while the first is still in flight.
    if (creating) return;
    const token = getAuthToken();
    if (!token) {
      setCreateError("No active session token was found. Please sign in again.");
      return;
    }
    try {
      setCreating(true);
      setCreateError(null);
      const created = await createAdminCategory(token, formValuesToPayload(createValues));
      closeCreate();
      setNotice(`Category "${created.name}" was created.`);
      // Re-read from the backend rather than splicing the response into the
      // current page: the list is ordered by name and server-paginated, so the
      // new row's real position is the backend's to decide.
      await fetchCategories();
    } catch (err) {
      setCreateError(
        err instanceof AdminApiError ? err.message : "Failed to create the category."
      );
    } finally {
      setCreating(false);
    }
  }, [creating, createValues, closeCreate, fetchCategories]);

  // --- Activate / deactivate ----------------------------------------------
  // PATCH { is_active } is the backend's own documented alternative to deleting
  // a category that products still reference.
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const toggleActive = useCallback(async (category: AdminCategory) => {
    const token = getAuthToken();
    if (!token) {
      setToggleError("No active session token was found. Please sign in again.");
      return;
    }
    try {
      setTogglingId(category.id);
      setToggleError(null);
      setNotice(null);
      const updated = await updateAdminCategory(token, category.id, {
        is_active: !category.is_active,
      });
      setCategories((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setNotice(
        `Category "${updated.name}" is now ${updated.is_active ? "active" : "inactive"}.`
      );
    } catch (err) {
      setToggleError(
        err instanceof AdminApiError ? err.message : "Failed to update the category."
      );
    } finally {
      setTogglingId(null);
    }
  }, []);

  const columns: AdminTableColumn<AdminCategory>[] = useMemo(
    () => [
      {
        key: "category",
        header: "Category",
        render: (category) => (
          <Link
            href={`/admin/categories/${category.id}`}
            className="font-bold text-ink hover:text-primary transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm inline-flex items-center gap-2"
          >
            {category.icon && (
              <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-ink-muted">
                {category.icon}
              </span>
            )}
            <span className="block line-clamp-1">{category.name}</span>
          </Link>
        ),
        width: "w-64",
      },
      {
        key: "slug",
        header: "Slug",
        render: (category) => <span className="font-mono text-[11px]">{category.slug}</span>,
        hideOnMobile: true,
      },
      {
        key: "products",
        header: "Products",
        render: (category) => category.products_count,
        align: "right",
        hideOnMobile: true,
        width: "w-24",
      },
      {
        key: "status",
        header: "Status",
        render: (category) => (
          <AdminStatusBadge
            status={null}
            label={category.is_active ? "Active" : "Inactive"}
            tone={category.is_active ? "success" : "neutral"}
          />
        ),
      },
      {
        key: "created",
        header: "Created",
        render: (category) => formatDate(category.created_at),
        hideOnMobile: true,
      },
    ],
    []
  );

  const actions: AdminRowAction<AdminCategory>[] = useMemo(
    () => [
      {
        key: "deactivate",
        label: "Deactivate",
        icon: "visibility_off",
        tone: "danger",
        onClick: toggleActive,
        isHidden: (category) => !category.is_active,
        isDisabled: (category) => togglingId === category.id,
      },
      {
        key: "activate",
        label: "Activate",
        icon: "visibility",
        tone: "primary",
        onClick: toggleActive,
        isHidden: (category) => category.is_active,
        isDisabled: (category) => togglingId === category.id,
      },
    ],
    [toggleActive, togglingId]
  );

  if (!canManage) {
    return <CategoryAccessNotice />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Categories</h1>
          <p className="text-xs text-ink-muted">
            Maintain the catalog taxonomy every product is filed under — create categories, edit
            them, and retire the ones that are no longer in use.
          </p>
        </div>
        {!createOpen && (
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold uppercase tracking-wide transition-colors shadow-xs shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              add
            </span>
            New Category
          </button>
        )}
      </div>

      {notice && (
        <div
          role="status"
          className="flex items-start gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-3.5 py-2.5"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-emerald-600">
            check_circle
          </span>
          <p className="text-xs font-semibold text-emerald-700 flex-1">{notice}</p>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="text-emerald-700 hover:text-emerald-900 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 rounded-sm"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              close
            </span>
            <span className="sr-only">Dismiss</span>
          </button>
        </div>
      )}

      {toggleError && (
        <p role="alert" className="text-xs font-semibold text-red-600">
          {toggleError}
        </p>
      )}

      {createOpen && (
        <section
          aria-label="Create category"
          className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6"
        >
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-4">
            New Category
          </h2>
          <CategoryForm
            idPrefix="create-category"
            values={createValues}
            onChange={setCreateValues}
            onSubmit={submitCreate}
            onCancel={closeCreate}
            submitting={creating}
            submitLabel="Create Category"
            error={createError}
            autoSlug
          />
        </section>
      )}

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} categor{totalCount === 1 ? "y" : "ies"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder="Search by name or slug…"
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-72"
        />
        <AdminSelectField
          label="Status"
          value={urlActive}
          options={ACTIVE_OPTIONS}
          onChange={(value) => updateParams({ is_active: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminCategory>
        caption="Catalog categories"
        columns={columns}
        rows={categories}
        getRowId={(category) => category.id}
        loading={loading}
        error={error ? error.message : null}
        onRetry={fetchCategories}
        emptyTitle="No categories found"
        emptyMessage={
          isFiltered
            ? "No categories match the current filters."
            : "No categories have been created yet."
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
    </div>
  );
}
