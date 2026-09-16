"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminUserListItem,
  createAdminSeller,
  getAdminUserDetail,
  getAdminUsers,
} from "@/lib/admin-api";
import { hasAnyPermission } from "@/lib/admin-auth";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { AdminConfirmModal } from "@/components/admin/shared";
import {
  SELLER_TYPE_OPTIONS,
  SellerAccessNotice,
  canManageAdminSellers,
  canViewAdminSellers,
} from "../sellerGovernance";

interface SelectedUserSummary {
  id: number;
  username: string;
  email: string;
  hasSellerProfile: boolean;
}

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

export default function AdminSellerCreatePage() {
  return (
    <Suspense fallback={<SellerCreateFallback />}>
      <AdminSellerCreatePageContent />
    </Suspense>
  );
}

function SellerCreateFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

function AdminSellerCreatePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user: actor } = useAuth();

  const canView = canViewAdminSellers(actor);
  const canManage = canManageAdminSellers(actor);
  const canListUsers = hasAnyPermission(actor, ADMIN_PERMISSIONS.usersView);

  const prefilledUserId = searchParams.get("user_id");

  const [selectedUser, setSelectedUser] = useState<SelectedUserSummary | null>(null);
  const [manualUserId, setManualUserId] = useState(prefilledUserId ?? "");
  const [prefillError, setPrefillError] = useState<string | null>(null);
  const [prefillLoading, setPrefillLoading] = useState(Boolean(prefilledUserId));

  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<AdminUserListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showResults, setShowResults] = useState(false);

  const [businessName, setBusinessName] = useState("");
  const [sellerType, setSellerType] = useState("FULL_SHOP_OWNER");
  const [businessEmail, setBusinessEmail] = useState("");
  const [businessPhone, setBusinessPhone] = useState("");
  const [taxId, setTaxId] = useState("");
  const [description, setDescription] = useState("");

  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Resolve a pre-filled ?user_id= (e.g. arriving from a user's detail page)
  // into a display-ready summary. Falls back to the raw id if the lookup
  // fails — the backend still validates it at submit time either way.
  useEffect(() => {
    if (!prefilledUserId || !canListUsers) {
      setPrefillLoading(false);
      return;
    }
    const token = getAuthToken();
    if (!token) {
      setPrefillLoading(false);
      return;
    }
    let cancelled = false;
    getAdminUserDetail(token, prefilledUserId)
      .then((detail) => {
        if (cancelled) return;
        setSelectedUser({
          id: detail.id,
          username: detail.username,
          email: detail.email,
          hasSellerProfile: detail.seller_profile !== null,
        });
        setPrefillError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setPrefillError(
          err instanceof AdminApiError ? err.message : "Failed to load the requested user."
        );
      })
      .finally(() => {
        if (!cancelled) setPrefillLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [prefilledUserId, canListUsers]);

  // Debounced user search, only when the operator can list users at all.
  useEffect(() => {
    if (!canListUsers) return;
    if (!searchInput.trim()) {
      setSearchResults([]);
      setSearchError(null);
      return;
    }
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    const handle = setTimeout(() => {
      setSearching(true);
      getAdminUsers(token, { search: searchInput.trim(), page: 1, page_size: 8 })
        .then((data) => {
          if (!cancelled) {
            setSearchResults(data.results);
            setSearchError(null);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setSearchResults([]);
            setSearchError(
              err instanceof AdminApiError ? err.message : "Failed to search users."
            );
          }
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [searchInput, canListUsers]);

  const selectUser = useCallback((row: AdminUserListItem) => {
    setSelectedUser({
      id: row.id,
      username: row.username,
      email: row.email,
      hasSellerProfile: row.seller_profile_id !== null,
    });
    setShowResults(false);
    setSearchInput("");
  }, []);

  const clearSelectedUser = useCallback(() => {
    setSelectedUser(null);
    setManualUserId("");
  }, []);

  const resolvedUserId = selectedUser?.id ?? (manualUserId.trim() ? Number(manualUserId.trim()) : null);
  const userIdValid = resolvedUserId !== null && Number.isInteger(resolvedUserId) && resolvedUserId > 0;

  const canSubmit = userIdValid && businessName.trim().length > 0;

  const submit = useCallback(
    async (reason: string) => {
      const token = getAuthToken();
      if (!token) {
        setError("No active session token was found. Please sign in again.");
        return;
      }
      if (submitting || !userIdValid || resolvedUserId === null) return;

      try {
        setSubmitting(true);
        setError(null);
        const created = await createAdminSeller(token, {
          user_id: resolvedUserId,
          business_name: businessName.trim(),
          seller_type: sellerType,
          business_email: businessEmail.trim(),
          business_phone: businessPhone.trim(),
          tax_id: taxId.trim(),
          description: description.trim(),
          reason,
        });
        setConfirming(false);
        router.push(`/admin/sellers/${created.id}`);
      } catch (err) {
        setError(err instanceof AdminApiError ? err.message : "Failed to create the seller profile.");
      } finally {
        setSubmitting(false);
      }
    },
    [
      submitting,
      userIdValid,
      resolvedUserId,
      businessName,
      sellerType,
      businessEmail,
      businessPhone,
      taxId,
      description,
      router,
    ]
  );

  const backLink = (
    <Link
      href="/admin/sellers"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Sellers
    </Link>
  );

  if (!canView) {
    return <SellerAccessNotice />;
  }

  if (!canManage) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              shield_lock
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">You are not authorized to create sellers</p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              Creating a seller profile requires{" "}
              <code className="font-mono text-[11px]">sellers.admin.manage</code>. You can still
              browse existing seller applications.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {backLink}

      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">New seller</h1>
        <p className="text-xs text-ink-muted max-w-3xl mt-1">
          Attaches a SellerProfile to an existing platform user — this does not create a user
          account. The profile always starts in{" "}
          <code className="font-mono text-[11px]">PENDING</code> status; approving, rejecting or
          activating it is a separate governance step from the sellers list.
        </p>
      </div>

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-5">
        {/* User selection */}
        <div>
          <p className={FIELD_LABEL_CLASS}>
            User <span className="text-red-600">*</span>
          </p>

          {prefillLoading ? (
            <p className="text-xs text-ink-muted">Loading the selected user…</p>
          ) : selectedUser ? (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface-alt/40 p-3">
              <div className="min-w-0">
                <p className="text-xs font-bold text-ink truncate">
                  {selectedUser.username}{" "}
                  <span className="font-normal text-ink-muted">#{selectedUser.id}</span>
                </p>
                <p className="text-[11px] text-ink-muted truncate">{selectedUser.email || "—"}</p>
                {selectedUser.hasSellerProfile && (
                  <p className="text-[11px] font-semibold text-amber-600 mt-1 flex items-center gap-1">
                    <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                      warning
                    </span>
                    This user already has a seller profile. The backend will refuse a second one.
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={clearSelectedUser}
                disabled={submitting}
                className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-line hover:bg-surface text-[11px] font-bold text-ink transition-colors cursor-pointer disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Change
              </button>
            </div>
          ) : canListUsers ? (
            <div className="relative">
              {prefillError && (
                <p className="text-xs text-red-600 mb-2">{prefillError}</p>
              )}
              <div className="relative">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-ink-faint absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                >
                  search
                </span>
                <input
                  type="search"
                  value={searchInput}
                  onChange={(e) => {
                    setSearchInput(e.target.value);
                    setShowResults(true);
                  }}
                  onFocus={() => setShowResults(true)}
                  placeholder="Search by username, email, or name…"
                  disabled={submitting}
                  className={`${FIELD_CONTROL_CLASS} pl-9`}
                />
              </div>
              {showResults && searchInput.trim() && (
                <div className="absolute z-10 mt-1 w-full max-h-64 overflow-y-auto rounded-xl border border-line bg-surface shadow-lg">
                  {searching ? (
                    <p className="px-3 py-3 text-xs text-ink-muted">Searching…</p>
                  ) : searchError ? (
                    <p className="px-3 py-3 text-xs text-red-600">{searchError}</p>
                  ) : searchResults.length === 0 ? (
                    <p className="px-3 py-3 text-xs text-ink-muted">No users match that search.</p>
                  ) : (
                    <ul>
                      {searchResults.map((row) => (
                        <li key={row.id}>
                          <button
                            type="button"
                            onClick={() => selectUser(row)}
                            className="w-full text-left px-3 py-2.5 hover:bg-surface-alt transition-colors cursor-pointer border-b border-line last:border-0"
                          >
                            <p className="text-xs font-bold text-ink flex items-center gap-1.5">
                              {row.username}
                              {row.seller_profile_id !== null && (
                                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-600">
                                  Already a seller
                                </span>
                              )}
                            </p>
                            <p className="text-[11px] text-ink-muted">{row.email || "—"}</p>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <p className="text-[10px] text-ink-faint mt-1">
                Start typing to search the user directory. The seller profile targets the account
                you select — it never creates a new one.
              </p>
            </div>
          ) : (
            <div>
              <input
                type="number"
                min={1}
                value={manualUserId}
                onChange={(e) => setManualUserId(e.target.value)}
                disabled={submitting}
                placeholder="User ID"
                className={FIELD_CONTROL_CLASS}
              />
              <p className="text-[10px] text-ink-faint mt-1">
                You don&apos;t hold <code className="font-mono">users.admin.view</code>, so the
                user directory can&apos;t be searched here — enter the numeric user ID directly.
                The backend still validates it exists.
              </p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="seller-business-name" className={FIELD_LABEL_CLASS}>
              Business name <span className="text-red-600">*</span>
            </label>
            <input
              id="seller-business-name"
              type="text"
              required
              disabled={submitting}
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              placeholder="Acme Trading Co."
              className={FIELD_CONTROL_CLASS}
            />
          </div>
          <div>
            <label htmlFor="seller-type" className={FIELD_LABEL_CLASS}>
              Seller type
            </label>
            <select
              id="seller-type"
              value={sellerType}
              disabled={submitting}
              onChange={(e) => setSellerType(e.target.value)}
              className={`${FIELD_CONTROL_CLASS} cursor-pointer`}
            >
              {SELLER_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="seller-business-email" className={FIELD_LABEL_CLASS}>
              Business email
            </label>
            <input
              id="seller-business-email"
              type="email"
              disabled={submitting}
              value={businessEmail}
              onChange={(e) => setBusinessEmail(e.target.value)}
              className={FIELD_CONTROL_CLASS}
            />
          </div>
          <div>
            <label htmlFor="seller-business-phone" className={FIELD_LABEL_CLASS}>
              Business phone
            </label>
            <input
              id="seller-business-phone"
              type="text"
              disabled={submitting}
              value={businessPhone}
              onChange={(e) => setBusinessPhone(e.target.value)}
              className={FIELD_CONTROL_CLASS}
            />
          </div>
        </div>

        <div>
          <label htmlFor="seller-tax-id" className={FIELD_LABEL_CLASS}>
            Tax ID
          </label>
          <input
            id="seller-tax-id"
            type="text"
            disabled={submitting}
            value={taxId}
            onChange={(e) => setTaxId(e.target.value)}
            className={FIELD_CONTROL_CLASS}
          />
        </div>

        <div>
          <label htmlFor="seller-description" className={FIELD_LABEL_CLASS}>
            Description
          </label>
          <textarea
            id="seller-description"
            rows={3}
            disabled={submitting}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={`${FIELD_CONTROL_CLASS} resize-y`}
          />
        </div>

        {error && (
          <p role="alert" className="text-xs font-semibold text-red-600">
            {error}
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            disabled={!canSubmit || submitting}
            onClick={() => {
              setError(null);
              setConfirming(true);
            }}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Create seller profile
          </button>
          <button
            type="button"
            onClick={() => router.push("/admin/sellers")}
            disabled={submitting}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Cancel
          </button>
        </div>
      </div>

      <AdminConfirmModal
        open={confirming}
        title="Create Seller Profile"
        message={
          <>
            Create a seller profile for{" "}
            <strong>{selectedUser ? selectedUser.username : `user #${resolvedUserId}`}</strong>{" "}
            with business name <strong>{businessName}</strong>?
            <span className="block mt-2 text-ink-muted">
              The profile is created in PENDING status. It is not automatically approved or
              activated.
            </span>
            {error && <span className="block mt-2 font-semibold text-red-600">{error}</span>}
          </>
        }
        confirmLabel="Create seller profile"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this seller profile is being created…"
        loading={submitting}
        onConfirm={submit}
        onCancel={() => {
          setConfirming(false);
          setError(null);
        }}
      />
    </div>
  );
}
