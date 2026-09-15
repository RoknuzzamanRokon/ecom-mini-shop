"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminCategory,
  deleteAdminCategory,
  getAdminCategoryDetail,
  updateAdminCategory,
} from "@/lib/admin-api";
import { formatDateTime } from "@/lib/admin-format";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import {
  CategoryAccessNotice,
  CategoryForm,
  canManageAdminCategories,
  categoryToFormValues,
  formValuesToPayload,
  type CategoryFormValues,
} from "../categoryGovernance";

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
    <div className="space-y-6" aria-busy="true" aria-label="Loading category detail">
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

export default function AdminCategoryDetailPage() {
  const params = useParams<{ id: string }>();
  const categoryId = params.id;
  const router = useRouter();
  const { user } = useAuth();

  const canManage = canManageAdminCategories(user);

  const [category, setCategory] = useState<AdminCategory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchCategory = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminCategoryDetail(token, categoryId);
      setCategory(data);
    } catch (err) {
      setCategory(null);
      setError(err instanceof Error ? err : new Error("Failed to load category."));
    } finally {
      setLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    if (!canManage) return;
    fetchCategory();
  }, [canManage, fetchCategory]);

  // --- Edit ---------------------------------------------------------------
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<CategoryFormValues | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const startEditing = useCallback(() => {
    if (!category) return;
    setEditValues(categoryToFormValues(category));
    setSaveError(null);
    setNotice(null);
    setEditing(true);
  }, [category]);

  const cancelEditing = useCallback(() => {
    setEditing(false);
    setEditValues(null);
    setSaveError(null);
  }, []);

  const submitEdit = useCallback(async () => {
    // `saving` also drives the form's disabled state, so a second submit cannot
    // be started while the first is still in flight.
    if (saving || !editValues || !category) return;
    const token = getAuthToken();
    if (!token) {
      setSaveError("No active session token was found. Please sign in again.");
      return;
    }
    try {
      setSaving(true);
      setSaveError(null);
      // The PATCH response is the authoritative serialized category; render it
      // rather than the values that were typed in.
      const updated = await updateAdminCategory(
        token,
        category.id,
        formValuesToPayload(editValues)
      );
      setCategory(updated);
      setEditing(false);
      setEditValues(null);
      setNotice("Category updated.");
    } catch (err) {
      setSaveError(err instanceof AdminApiError ? err.message : "Failed to update the category.");
    } finally {
      setSaving(false);
    }
  }, [saving, editValues, category]);

  // --- Delete -------------------------------------------------------------
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const confirmDelete = useCallback(async () => {
    if (!category) return;
    const token = getAuthToken();
    if (!token) {
      setDeleteError("No active session token was found. Please sign in again.");
      return;
    }
    try {
      setDeleteError(null);
      await deleteAdminCategory(token, category.id);
      // Deleted for real — there is no record left to show.
      router.replace("/admin/categories");
    } catch (err) {
      // The dependency safeguard lands here as a 400 with the backend's own
      // explanation ("...referenced by N product(s). Deactivate the category
      // instead."). It is shown verbatim and never worked around.
      setDeleteError(
        err instanceof AdminApiError ? err.message : "Failed to delete the category."
      );
    }
  }, [category, router]);

  const backLink = (
    <Link
      href="/admin/categories"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Categories
    </Link>
  );

  if (!canManage) {
    return <CategoryAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !category) {
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
              {isNotFound ? "Category not found" : "Unable to load category"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This category does not exist or may have been deleted."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchCategory}
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

  const hasProducts = category.products_count > 0;
  const canSeeProducts = hasAnyPermission(user, ADMIN_PERMISSIONS.productsView);

  return (
    <div className="space-y-6">
      {backLink}

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

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              {category.icon && (
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[24px] text-ink-muted"
                >
                  {category.icon}
                </span>
              )}
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {category.name}
              </h1>
              <AdminStatusBadge
                status={null}
                label={category.is_active ? "Active" : "Inactive"}
                tone={category.is_active ? "success" : "neutral"}
              />
            </div>
            <p className="text-xs text-ink-muted mt-1 font-mono">{category.slug}</p>
            <p className="text-[11px] text-ink-muted mt-2">Category ID #{category.id}</p>
          </div>

          {!editing && (
            <div className="flex flex-wrap gap-2 shrink-0">
              <button
                type="button"
                onClick={startEditing}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  edit
                </span>
                Edit
              </button>
              <button
                type="button"
                onClick={() => {
                  setDeleteError(null);
                  setDeleteOpen(true);
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  delete
                </span>
                Delete
              </button>
            </div>
          )}
        </div>

        {category.description && !editing && (
          <p className="text-xs text-ink-muted leading-relaxed mt-4 pt-4 border-t border-line whitespace-pre-line">
            {category.description}
          </p>
        )}

        {hasProducts && !editing && (
          <p className="text-[11px] text-ink-muted mt-4 pt-4 border-t border-line flex items-start gap-1.5">
            <span aria-hidden="true" className="material-symbols-outlined text-[16px] text-amber-600">
              info
            </span>
            <span>
              This category is referenced by {category.products_count} product
              {category.products_count === 1 ? "" : "s"}, so the backend will refuse to delete it.
              Deactivate it instead to hide it from the public catalog.
            </span>
          </p>
        )}
      </div>

      {editing && editValues && (
        <section
          aria-label="Edit category"
          className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6"
        >
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-4">
            Edit Category
          </h2>
          <CategoryForm
            idPrefix="edit-category"
            values={editValues}
            onChange={setEditValues}
            onSubmit={submitEdit}
            onCancel={cancelEditing}
            submitting={saving}
            submitLabel="Save Changes"
            error={saveError}
            autoSlug={false}
          />
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Identity */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Identity
          </h2>
          <dl>
            <InfoRow label="Name" value={category.name} />
            <InfoRow
              label="Slug"
              value={<span className="font-mono">{category.slug}</span>}
            />
            <InfoRow
              label="Icon"
              value={category.icon ? <span className="font-mono">{category.icon}</span> : "—"}
            />
            <InfoRow
              label="Image"
              value={
                category.image ? (
                  <span className="font-mono break-all">{category.image}</span>
                ) : (
                  "—"
                )
              }
            />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            The category image is an upload field and is shown read-only here; this console sends
            JSON, not multipart form data.
          </p>
        </div>

        {/* Catalog */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Catalog
          </h2>
          <dl>
            <InfoRow
              label="Products"
              value={`${category.products_count} product${category.products_count === 1 ? "" : "s"}`}
            />
            <InfoRow
              label="Visibility"
              value={
                category.is_active
                  ? "Active — eligible for the public catalog"
                  : "Inactive — hidden from the public catalog"
              }
            />
          </dl>
          {canSeeProducts && hasProducts && (
            <Link
              href={`/admin/products?category=${category.id}`}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                inventory_2
              </span>
              View products in this category
            </Link>
          )}
        </div>

        {/* Metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 lg:col-span-2">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Metadata
          </h2>
          <dl>
            <InfoRow label="Created" value={formatDateTime(category.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(category.updated_at)} />
          </dl>
        </div>
      </div>

      <AdminConfirmModal
        open={deleteOpen}
        title="Delete Category"
        message={
          <>
            {hasProducts ? (
              <>
                {`"${category.name}" is referenced by ${category.products_count} product${
                  category.products_count === 1 ? "" : "s"
                }. The backend protects categories that are still in use, so this will be refused — deactivate it instead.`}
              </>
            ) : (
              `Permanently delete "${category.name}"? This is a hard delete and cannot be undone.`
            )}
            {deleteError && <p className="mt-2 font-semibold text-red-600">{deleteError}</p>}
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
        onCancel={() => {
          setDeleteOpen(false);
          setDeleteError(null);
        }}
      />
    </div>
  );
}
