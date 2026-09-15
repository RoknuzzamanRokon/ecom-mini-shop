"use client";

/**
 * Category Governance feature helpers (Phase 1E).
 *
 * Colocated with the /admin/categories routes — feature-local, not a generic
 * Phase 1A shared component. It holds:
 *   - the permission gate mirroring CanManageAdminCategories,
 *   - a slug pre-fill that mirrors django.utils.text.slugify,
 *   - the shared category form used by both create and edit,
 *   - the page-level access notice both routes render.
 *
 * Nothing here talks to the network except through admin-api.ts, and nothing
 * here is a security boundary — the backend authorizes every mutation itself.
 */

import React from "react";
import Link from "next/link";
import type { AuthUser } from "@/lib/types";
import type { AdminCategory, AdminCategoryWritePayload } from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";

/**
 * Page access gate, mirroring CanManageAdminCategories.
 *
 * Unlike shops / sellers / products there is no read-only split: seed_rbac.py
 * seeds exactly one category permission, 'categories.admin.manage', so viewing
 * the taxonomy and editing it are the same privilege. Being a management user
 * is NOT sufficient — AdminGuard only establishes console eligibility.
 */
export function canManageAdminCategories(user: AuthUser | null | undefined): boolean {
  return hasAnyPermission(user, ADMIN_PERMISSIONS.categoriesManage);
}

/**
 * Mirrors django.utils.text.slugify(value, allow_unicode=False):
 *   NFKD normalise -> drop non-ASCII -> lowercase
 *   -> strip everything except [A-Za-z0-9_], whitespace and hyphen
 *   -> collapse runs of hyphen/whitespace to one hyphen
 *   -> trim leading/trailing hyphens and underscores.
 *
 * This only PRE-FILLS the slug field, which the operator can always overwrite.
 * AdminCategorySerializer marks `slug` required (Category.slug is not
 * blank=True), so Category.save()'s own auto-slugify never runs through the
 * API and a value has to be supplied. Uniqueness and final validity remain the
 * backend's decision — this never tries to pre-empt it.
 */
export function slugifyLikeDjango(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/[-\s]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "");
}

export interface CategoryFormValues {
  name: string;
  slug: string;
  icon: string;
  description: string;
  is_active: boolean;
}

export const EMPTY_CATEGORY_FORM: CategoryFormValues = {
  name: "",
  slug: "",
  icon: "",
  description: "",
  is_active: true,
};

export function categoryToFormValues(category: AdminCategory): CategoryFormValues {
  return {
    name: category.name,
    slug: category.slug,
    icon: category.icon,
    description: category.description,
    is_active: category.is_active,
  };
}

/** Trims text fields so the backend never stores incidental whitespace. */
export function formValuesToPayload(values: CategoryFormValues): AdminCategoryWritePayload {
  return {
    name: values.name.trim(),
    slug: values.slug.trim(),
    icon: values.icon.trim(),
    description: values.description.trim(),
    is_active: values.is_active,
  };
}

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

export interface CategoryFormProps {
  values: CategoryFormValues;
  onChange: (values: CategoryFormValues) => void;
  onSubmit: () => void;
  onCancel: () => void;
  /** Disables every control and the submit button while the request is in flight. */
  submitting: boolean;
  submitLabel: string;
  /** Backend error text, rendered verbatim above the buttons. */
  error: string | null;
  /**
   * Create keeps name and slug linked so the required slug fills itself in;
   * edit does not, because silently rewriting a live slug would break the
   * public /category/<slug> URLs the storefront already serves.
   */
  autoSlug: boolean;
  idPrefix: string;
}

/**
 * The category form shared by the create panel and the detail edit panel.
 *
 * Client-side validation is limited to "required fields are non-empty", purely
 * so the operator gets instant feedback. Everything else — slug format,
 * uniqueness, length — is left to the serializer, and its errors are surfaced
 * through `error` rather than guessed at here.
 */
export function CategoryForm({
  values,
  onChange,
  onSubmit,
  onCancel,
  submitting,
  submitLabel,
  error,
  autoSlug,
  idPrefix,
}: CategoryFormProps) {
  const nameId = `${idPrefix}-name`;
  const slugId = `${idPrefix}-slug`;
  const iconId = `${idPrefix}-icon`;
  const descriptionId = `${idPrefix}-description`;
  const activeId = `${idPrefix}-active`;
  const errorId = `${idPrefix}-error`;

  const canSubmit = values.name.trim().length > 0 && values.slug.trim().length > 0 && !submitting;

  const handleNameChange = (name: string) => {
    onChange(
      autoSlug ? { ...values, name, slug: slugifyLikeDjango(name) } : { ...values, name }
    );
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
      className="space-y-4"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={nameId} className={FIELD_LABEL_CLASS}>
            Name <span className="text-red-600">*</span>
          </label>
          <input
            id={nameId}
            type="text"
            required
            value={values.name}
            disabled={submitting}
            onChange={(e) => handleNameChange(e.target.value)}
            className={FIELD_CONTROL_CLASS}
            placeholder="Electronics"
          />
        </div>

        <div>
          <label htmlFor={slugId} className={FIELD_LABEL_CLASS}>
            Slug <span className="text-red-600">*</span>
          </label>
          <input
            id={slugId}
            type="text"
            required
            value={values.slug}
            disabled={submitting}
            onChange={(e) => onChange({ ...values, slug: e.target.value })}
            aria-describedby={`${slugId}-help`}
            className={`${FIELD_CONTROL_CLASS} font-mono`}
            placeholder="electronics"
          />
          <p id={`${slugId}-help`} className="text-[10px] text-ink-faint mt-1">
            {autoSlug
              ? "Filled in from the name; edit it if you need a different URL."
              : "Changing this changes the public category URL."}
          </p>
        </div>

        <div>
          <label htmlFor={iconId} className={FIELD_LABEL_CLASS}>
            Icon
          </label>
          <input
            id={iconId}
            type="text"
            value={values.icon}
            disabled={submitting}
            onChange={(e) => onChange({ ...values, icon: e.target.value })}
            aria-describedby={`${iconId}-help`}
            className={`${FIELD_CONTROL_CLASS} font-mono`}
            placeholder="checkroom"
          />
          <p id={`${iconId}-help`} className="text-[10px] text-ink-faint mt-1">
            Material Symbols name, as the model&apos;s help text describes.
          </p>
        </div>

        <div className="flex items-end">
          <div className="flex items-center gap-2.5 pb-2">
            <input
              id={activeId}
              type="checkbox"
              checked={values.is_active}
              disabled={submitting}
              onChange={(e) => onChange({ ...values, is_active: e.target.checked })}
              className="w-4 h-4 rounded border-line text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary cursor-pointer disabled:cursor-not-allowed"
            />
            <label htmlFor={activeId} className="text-xs font-bold text-ink cursor-pointer">
              Active
              <span className="block text-[10px] font-medium text-ink-muted">
                Inactive categories are hidden from the public catalog.
              </span>
            </label>
          </div>
        </div>
      </div>

      <div>
        <label htmlFor={descriptionId} className={FIELD_LABEL_CLASS}>
          Description
        </label>
        <textarea
          id={descriptionId}
          rows={3}
          value={values.description}
          disabled={submitting}
          onChange={(e) => onChange({ ...values, description: e.target.value })}
          className={`${FIELD_CONTROL_CLASS} resize-y`}
          placeholder="Short description used on category banners and headers."
        />
      </div>

      {error && (
        <p id={errorId} role="alert" className="text-xs font-semibold text-red-600">
          {error}
        </p>
      )}

      <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="px-4 py-2 rounded-lg border border-line text-xs font-bold text-ink hover:bg-surface-alt transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!canSubmit}
          aria-describedby={error ? errorId : undefined}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {submitting && (
            <span className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-current" />
          )}
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

/**
 * Page-level "you may not open this module" panel.
 *
 * Hiding the sidebar entry does not stop somebody typing the URL, so both
 * category routes render this instead of fetching when the operator lacks the
 * permission. It is a UX courtesy only: the backend would return 403 for the
 * request regardless.
 */
export function CategoryAccessNotice() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            shield_lock
          </span>
        </div>
        <h1 className="text-xl font-black text-ink tracking-tight mb-2">
          Insufficient Permissions
        </h1>
        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          Your account does not hold the permission required to open{" "}
          <strong className="text-ink">Categories</strong>. Taxonomy governance requires{" "}
          <code className="font-mono text-[11px]">categories.admin.manage</code>. Contact a
          Super Administrator if you believe this is incorrect.
        </p>
        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}
