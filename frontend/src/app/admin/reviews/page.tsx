"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminReview, AdminReviewType, getAdminReviews } from "@/lib/admin-api";
import { formatDate } from "@/lib/admin-format";
import type { PaginatedResponse } from "@/lib/types";
import StarRating from "@/components/reviews/StarRating";
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
  MODERATION_COPY,
  RATING_OPTIONS,
  REVIEW_TYPE_TABS,
  ReviewAccessNotice,
  VISIBILITY_OPTIONS,
  canModerateReviews,
  useReviewModeration,
} from "./reviewGovernance";

/** Matches AdminPagination.page_size in shop/admin_views.py. */
const PAGE_SIZE = 20;

export default function AdminReviewsPage() {
  return (
    <Suspense fallback={<ReviewsPageFallback />}>
      <AdminReviewsPageContent />
    </Suspense>
  );
}

function ReviewsPageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

/** A fetch result, stored with the key of the request that produced it. */
interface ListState {
  key: string;
  data?: PaginatedResponse<AdminReview>;
  error?: string;
}

function AdminReviewsPageContent() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canView = canModerateReviews(user);

  const urlType: AdminReviewType = searchParams.get("type") === "shop" ? "shop" : "product";
  const urlSearch = searchParams.get("search") ?? "";
  const urlRating = searchParams.get("rating") ?? "";
  const rawHidden = searchParams.get("hidden");
  const urlHidden = rawHidden === "true" || rawHidden === "false" ? rawHidden : "";
  const urlPage = Number(searchParams.get("page") ?? "1") || 1;

  // Local text state so typing feels instant; committed to the URL after a
  // short debounce, and resynced from the URL during render when it changes
  // externally (back/forward, "Clear filters").
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
      if (searchInput !== urlSearch) updateParams({ search: searchInput || null, page: null });
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput, urlSearch, updateParams]);

  const [reloadToken, setReloadToken] = useState(0);
  const [list, setList] = useState<ListState | null>(null);
  const requestKey = `${urlType}|${urlSearch}|${urlRating}|${urlHidden}|${urlPage}|${reloadToken}`;

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    const token = getAuthToken();
    const request = token
      ? getAdminReviews(token, urlType, {
          search: urlSearch || undefined,
          rating: urlRating || undefined,
          hidden: urlHidden || undefined,
          page: urlPage,
        })
      : Promise.reject(new Error("No active session token was found. Please sign in again."));
    request
      .then((data) => {
        if (!cancelled) setList({ key: requestKey, data });
      })
      .catch((err) => {
        if (!cancelled) {
          setList({ key: requestKey, error: err instanceof Error ? err.message : "Failed to load reviews." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canView, requestKey, urlType, urlSearch, urlRating, urlHidden, urlPage]);

  const loading = list?.key !== requestKey;
  const reviews = !loading ? list?.data?.results ?? [] : [];
  const totalCount = !loading ? list?.data?.count ?? 0 : 0;
  const error = !loading ? list?.error ?? null : null;

  const isFiltered = Boolean(urlSearch || urlRating || urlHidden);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    updateParams({ search: null, rating: null, hidden: null, page: null });
  }, [updateParams]);

  // The API response is authoritative; merge it into the loaded page.
  const handleModerated = useCallback((updated: AdminReview) => {
    setList((prev) =>
      prev?.data
        ? {
            ...prev,
            data: {
              ...prev.data,
              results: prev.data.results.map((r) => (r.id === updated.id ? updated : r)),
            },
          }
        : prev
    );
  }, []);
  const { pending, submitError, request, cancel, confirm } = useReviewModeration(
    urlType,
    handleModerated
  );

  const columns: AdminTableColumn<AdminReview>[] = useMemo(
    () => [
      {
        key: "review",
        header: "Review",
        render: (review) => (
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2">
              <StarRating rating={review.rating} size={13} />
              {review.is_verified_purchase && (
                <span className="text-[10px] font-bold uppercase tracking-wide text-success">
                  Verified
                </span>
              )}
            </div>
            <p className="text-xs text-ink-body line-clamp-2">
              {review.comment || <span className="italic text-ink-muted">No comment</span>}
            </p>
          </div>
        ),
        width: "w-80",
      },
      {
        key: "target",
        header: urlType === "shop" ? "Shop" : "Product",
        render: (review) => (
          <Link
            href={`/${urlType === "shop" ? "shop" : "product"}/${review.target.slug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold text-ink hover:text-primary transition-colors line-clamp-1"
          >
            {review.target.name}
          </Link>
        ),
      },
      {
        key: "author",
        header: "Author",
        render: (review) => <span className="font-mono text-[11px]">{review.author.username}</span>,
        hideOnMobile: true,
      },
      {
        key: "status",
        header: "Status",
        render: (review) =>
          review.is_hidden ? (
            <div className="flex flex-col items-start gap-1">
              <AdminStatusBadge status="HIDDEN" label="Hidden" tone="danger" />
              <span className="text-[11px] text-ink-muted line-clamp-2">
                {review.hidden_reason}
                {review.hidden_by_username && ` — ${review.hidden_by_username}`}
              </span>
            </div>
          ) : (
            <AdminStatusBadge status="VISIBLE" label="Visible" tone="success" />
          ),
      },
      {
        key: "created",
        header: "Posted",
        render: (review) => formatDate(review.created_at),
        hideOnMobile: true,
      },
    ],
    [urlType]
  );

  const actions: AdminRowAction<AdminReview>[] = useMemo(
    () => [
      {
        key: "hide",
        label: "Hide",
        icon: "visibility_off",
        tone: "danger",
        onClick: (review) => request(review, "hide"),
        isHidden: (review) => review.is_hidden,
      },
      {
        key: "unhide",
        label: "Restore",
        icon: "visibility",
        tone: "primary",
        onClick: (review) => request(review, "unhide"),
        isHidden: (review) => !review.is_hidden,
      },
    ],
    [request]
  );

  if (!canView) {
    return <ReviewAccessNotice />;
  }

  const copy = pending ? MODERATION_COPY[pending.action] : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">Reviews</h1>
        <p className="text-xs text-ink-muted">
          Hide abusive or spam reviews from the storefront, or restore them. Hidden reviews stay on
          record and stay visible to their authors; they are left out of public lists and ratings.
        </p>
      </div>

      <div role="tablist" aria-label="Review type" className="flex gap-2">
        {REVIEW_TYPE_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={urlType === tab.value}
            onClick={() => updateParams({ type: tab.value === "product" ? null : tab.value, page: null })}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors cursor-pointer ${
              urlType === tab.value
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface text-ink border-line hover:bg-surface-alt"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <AdminFilterBar
        isDirty={isFiltered}
        onReset={clearFilters}
        trailing={
          !loading &&
          !error && (
            <span className="text-xs font-semibold text-ink-muted whitespace-nowrap">
              {totalCount.toLocaleString("en-US")} review{totalCount === 1 ? "" : "s"}
            </span>
          )
        }
      >
        <AdminSearchField
          label="Search"
          placeholder={`Search comment, author or ${urlType === "shop" ? "shop" : "product"}…`}
          value={searchInput}
          onChange={setSearchInput}
          className="sm:w-80"
        />
        <AdminSelectField
          label="Rating"
          value={urlRating}
          options={RATING_OPTIONS}
          onChange={(value) => updateParams({ rating: value || null, page: null })}
        />
        <AdminSelectField
          label="Visibility"
          value={urlHidden}
          options={VISIBILITY_OPTIONS}
          onChange={(value) => updateParams({ hidden: value || null, page: null })}
        />
      </AdminFilterBar>

      <AdminDataTable<AdminReview>
        caption={urlType === "shop" ? "Shop reviews" : "Product reviews"}
        columns={columns}
        rows={reviews}
        getRowId={(review) => review.id}
        loading={loading}
        error={error}
        onRetry={() => setReloadToken((t) => t + 1)}
        emptyTitle="No reviews found"
        emptyMessage={
          isFiltered ? "No reviews match the current filters." : "Nobody has written a review of this type yet."
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
        open={Boolean(pending)}
        title={copy?.title ?? ""}
        message={
          <>
            {pending && copy ? copy.message(pending.review) : ""}
            {submitError && <p className="mt-2 font-semibold text-accent">{submitError}</p>}
          </>
        }
        confirmLabel={copy?.label ?? "Confirm"}
        destructive={copy?.destructive ?? false}
        requireReason={pending?.action === "hide"}
        reasonRequired={pending?.action === "hide"}
        reasonLabel="Reason"
        reasonPlaceholder="Why is this review being hidden? The author will see this…"
        onConfirm={confirm}
        onCancel={cancel}
      />
    </div>
  );
}
