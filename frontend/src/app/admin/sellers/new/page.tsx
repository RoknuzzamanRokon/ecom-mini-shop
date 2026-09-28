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
  canCreateAdminSellers,
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

type AccountMode = "existing" | "new";

const ACCOUNT_MODES: { value: AccountMode; label: string; icon: string }[] = [
  { value: "existing", label: "Existing user", icon: "person_search" },
  { value: "new", label: "New account", icon: "person_add" },
];

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
  const canCreate = canCreateAdminSellers(actor);
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

  // "new" creates the login account in the same request (AdminSellerCreateSerializer.account).
  const [accountMode, setAccountMode] = useState<AccountMode>("existing");
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newFirstName, setNewFirstName] = useState("");
  const [newLastName, setNewLastName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);

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

  const passwordMismatch = newPasswordConfirm.length > 0 && newPassword !== newPasswordConfirm;
  const newAccountValid =
    newUsername.trim().length > 0 &&
    newEmail.trim().length > 0 &&
    newPassword.length > 0 &&
    newPassword === newPasswordConfirm;
  const accountValid = accountMode === "new" ? newAccountValid : userIdValid;

  const canSubmit = accountValid && businessName.trim().length > 0;

  const submit = useCallback(
    async (reason: string) => {
      const token = getAuthToken();
      if (!token) {
        setError("No active session token was found. Please sign in again.");
        return;
      }
      const target =
        accountMode === "new"
          ? {
              account: {
                username: newUsername.trim(),
                email: newEmail.trim(),
                password: newPassword,
                password_confirm: newPasswordConfirm,
                first_name: newFirstName.trim(),
                last_name: newLastName.trim(),
              },
            }
          : resolvedUserId !== null
          ? { user_id: resolvedUserId }
          : null;
      if (submitting || !accountValid || !target) return;

      try {
        setSubmitting(true);
        setError(null);
        const created = await createAdminSeller(token, {
          ...target,
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
      accountMode,
      accountValid,
      resolvedUserId,
      newUsername,
      newEmail,
      newPassword,
      newPasswordConfirm,
      newFirstName,
      newLastName,
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

  if (!canCreate) {
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
              <code className="font-mono text-[11px]">sellers.create</code> or{" "}
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
          Attach a seller profile to an existing platform user, or create a new login account for
          the seller at the same time. The profile always starts in{" "}
          <code className="font-mono text-[11px]">PENDING</code> status; approving, rejecting or
          activating it is a separate governance step from the sellers list.
        </p>
      </div>

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-5">
        {/* User selection */}
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2">
            <p className="text-[10px] font-extrabold uppercase tracking-wider text-ink-muted">
              Seller account <span className="text-danger">*</span>
            </p>
            <div
              role="group"
              aria-label="Seller account source"
              className="inline-flex self-start rounded-lg border border-line bg-surface-alt/40 p-0.5"
            >
              {ACCOUNT_MODES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={accountMode === option.value}
                  disabled={submitting}
                  onClick={() => {
                    setAccountMode(option.value);
                    setError(null);
                  }}
                  className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-[11px] font-bold transition-colors cursor-pointer disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary ${
                    accountMode === option.value
                      ? "bg-primary text-on-primary shadow-xs"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    {option.icon}
                  </span>
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {accountMode === "new" ? (
            <div className="rounded-xl border border-line bg-surface-alt/40 p-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="new-account-username" className={FIELD_LABEL_CLASS}>
                    Username <span className="text-danger">*</span>
                  </label>
                  <input
                    id="new-account-username"
                    type="text"
                    required
                    maxLength={150}
                    autoComplete="off"
                    disabled={submitting}
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div>
                  <label htmlFor="new-account-email" className={FIELD_LABEL_CLASS}>
                    Email <span className="text-danger">*</span>
                  </label>
                  <input
                    id="new-account-email"
                    type="email"
                    required
                    maxLength={254}
                    autoComplete="off"
                    disabled={submitting}
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div>
                  <label htmlFor="new-account-first-name" className={FIELD_LABEL_CLASS}>
                    First name
                  </label>
                  <input
                    id="new-account-first-name"
                    type="text"
                    maxLength={150}
                    autoComplete="off"
                    disabled={submitting}
                    value={newFirstName}
                    onChange={(e) => setNewFirstName(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div>
                  <label htmlFor="new-account-last-name" className={FIELD_LABEL_CLASS}>
                    Last name
                  </label>
                  <input
                    id="new-account-last-name"
                    type="text"
                    maxLength={150}
                    autoComplete="off"
                    disabled={submitting}
                    value={newLastName}
                    onChange={(e) => setNewLastName(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div>
                  <label htmlFor="new-account-password" className={FIELD_LABEL_CLASS}>
                    Password <span className="text-danger">*</span>
                  </label>
                  <input
                    id="new-account-password"
                    type={showPassword ? "text" : "password"}
                    required
                    autoComplete="new-password"
                    disabled={submitting}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                </div>
                <div>
                  <label htmlFor="new-account-password-confirm" className={FIELD_LABEL_CLASS}>
                    Confirm password <span className="text-danger">*</span>
                  </label>
                  <input
                    id="new-account-password-confirm"
                    type={showPassword ? "text" : "password"}
                    required
                    autoComplete="new-password"
                    disabled={submitting}
                    value={newPasswordConfirm}
                    onChange={(e) => setNewPasswordConfirm(e.target.value)}
                    aria-invalid={passwordMismatch}
                    className={FIELD_CONTROL_CLASS}
                  />
                  {passwordMismatch && (
                    <p className="text-[11px] text-danger mt-1">Passwords do not match.</p>
                  )}
                </div>
              </div>
              <label className="inline-flex items-center gap-2 text-[11px] font-semibold text-ink-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={showPassword}
                  onChange={(e) => setShowPassword(e.target.checked)}
                  className="accent-primary"
                />
                Show password
              </label>
              <p className="text-[10px] text-ink-faint">
                Creates a login account with no roles and no staff access. The seller signs in with
                this username and password. The backend checks that the username and email are not
                already taken and applies the platform password rules.
              </p>
            </div>
          ) : prefillLoading ? (
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
            {accountMode === "new" ? "Create account & seller" : "Create seller profile"}
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
        title={accountMode === "new" ? "Create Account & Seller Profile" : "Create Seller Profile"}
        message={
          <>
            {accountMode === "new" ? (
              <>
                Create a new account <strong>{newUsername.trim()}</strong> ({newEmail.trim()}) and
                a seller profile with business name <strong>{businessName}</strong>?
              </>
            ) : (
              <>
                Create a seller profile for{" "}
                <strong>{selectedUser ? selectedUser.username : `user #${resolvedUserId}`}</strong>{" "}
                with business name <strong>{businessName}</strong>?
              </>
            )}
            <span className="block mt-2 text-ink-muted">
              {accountMode === "new" && "The account has no roles or staff access. "}
              The profile is created in PENDING status. It is not automatically approved or
              activated.
            </span>
            {error && <span className="block mt-2 font-semibold text-red-600">{error}</span>}
          </>
        }
        confirmLabel={accountMode === "new" ? "Create account & seller" : "Create seller profile"}
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
