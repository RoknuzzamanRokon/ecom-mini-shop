"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminSeller,
  createAdminShop,
  getAdminSellers,
} from "@/lib/admin-api";
import { ADMIN_PERMISSIONS } from "@/lib/admin-navigation";
import { hasAnyPermission } from "@/lib/admin-auth";
import { AdminConfirmModal } from "@/components/admin/shared";
import UseCurrentLocationButton, {
  CoordinateMapLink,
} from "@/components/location/UseCurrentLocationButton";
import { ShopAccessNotice, canManageAdminShops, canViewAdminShops } from "../shopGovernance";

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

/**
 * Ineligibility hint shown next to a candidate seller, mirroring the exact
 * rules in shops.services.ShopService.validate_seller_eligibility_for_creation.
 * Advisory only — the backend re-validates and is authoritative; this just
 * saves the operator a round trip for the common cases.
 */
function eligibilityWarning(seller: AdminSeller): string | null {
  if (!seller.is_operational) {
    return `This seller's account is currently '${seller.status}'. Only an operational (APPROVED or ACTIVE) seller can own a shop.`;
  }
  if (seller.seller_type === "PRODUCT_OWNER") {
    return "Product Owners are not permitted to own shops under system business rules.";
  }
  if (seller.seller_type === "LIMITED_SHOP_OWNER" && seller.shops_count >= 1) {
    return "This Limited Shop Owner already owns a shop and is capped at 1.";
  }
  return null;
}

export default function AdminShopCreatePage() {
  const router = useRouter();
  const { user: actor } = useAuth();

  const canView = canViewAdminShops(actor);
  const canManage = canManageAdminShops(actor);
  const canListSellers = hasAnyPermission(actor, ADMIN_PERMISSIONS.sellersView);

  const [selectedSeller, setSelectedSeller] = useState<AdminSeller | null>(null);
  const [manualSellerId, setManualSellerId] = useState("");

  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<AdminSeller[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showResults, setShowResults] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");

  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounced seller search, only when the operator can list sellers at all.
  useEffect(() => {
    if (!canListSellers) return;
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
      getAdminSellers(token, { search: searchInput.trim(), page: 1, page_size: 8 })
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
              err instanceof AdminApiError ? err.message : "Failed to search sellers."
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
  }, [searchInput, canListSellers]);

  const selectSeller = useCallback((row: AdminSeller) => {
    setSelectedSeller(row);
    setShowResults(false);
    setSearchInput("");
  }, []);

  const clearSelectedSeller = useCallback(() => {
    setSelectedSeller(null);
    setManualSellerId("");
  }, []);

  const resolvedSellerId =
    selectedSeller?.id ?? (manualSellerId.trim() ? Number(manualSellerId.trim()) : null);
  const sellerIdValid =
    resolvedSellerId !== null && Number.isInteger(resolvedSellerId) && resolvedSellerId > 0;

  const latLngBothOrNeither =
    (latitude.trim() === "") === (longitude.trim() === "");

  const canSubmit = sellerIdValid && name.trim().length > 0 && latLngBothOrNeither;

  const submit = useCallback(
    async (reason: string) => {
      const token = getAuthToken();
      if (!token) {
        setError("No active session token was found. Please sign in again.");
        return;
      }
      if (submitting || !sellerIdValid || resolvedSellerId === null) return;

      try {
        setSubmitting(true);
        setError(null);
        const created = await createAdminShop(token, {
          seller_id: resolvedSellerId,
          name: name.trim(),
          description: description.trim(),
          phone: phone.trim(),
          address: address.trim(),
          latitude: latitude.trim() ? Number(latitude.trim()) : undefined,
          longitude: longitude.trim() ? Number(longitude.trim()) : undefined,
          reason,
        });
        setConfirming(false);
        router.push(`/admin/shops/${created.id}`);
      } catch (err) {
        setError(err instanceof AdminApiError ? err.message : "Failed to create the shop.");
      } finally {
        setSubmitting(false);
      }
    },
    [
      submitting,
      sellerIdValid,
      resolvedSellerId,
      name,
      description,
      phone,
      address,
      latitude,
      longitude,
      router,
    ]
  );

  const backLink = (
    <Link
      href="/admin/shops"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Shops
    </Link>
  );

  if (!canView) {
    return <ShopAccessNotice />;
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
            <p className="text-sm font-bold text-ink">You are not authorized to create shops</p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              Creating a shop requires{" "}
              <code className="font-mono text-[11px]">shops.admin.manage</code>. You can still
              browse existing shops.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const warning = selectedSeller ? eligibilityWarning(selectedSeller) : null;

  return (
    <div className="space-y-6">
      {backLink}

      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">New shop</h1>
        <p className="text-xs text-ink-muted max-w-3xl mt-1">
          Creates a Shop and assigns an existing seller as its owner in one step — the
          Admin-created Shop Owner model. The seller does not create shops from the Seller
          Panel; they only see and manage the shop assigned to them here. The shop always
          starts in <code className="font-mono text-[11px]">DRAFT</code> status; approving or
          activating it is a separate step from the shops list.
        </p>
      </div>

      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-5">
        {/* Seller selection */}
        <div>
          <p className={FIELD_LABEL_CLASS}>
            Owner (Seller) <span className="text-red-600">*</span>
          </p>

          {selectedSeller ? (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface-alt/40 p-3">
              <div className="min-w-0">
                <p className="text-xs font-bold text-ink truncate">
                  {selectedSeller.business_name}{" "}
                  <span className="font-normal text-ink-muted">#{selectedSeller.id}</span>
                </p>
                <p className="text-[11px] text-ink-muted truncate">
                  {selectedSeller.username} &middot; {selectedSeller.seller_type} &middot;{" "}
                  {selectedSeller.status}
                </p>
                {warning && (
                  <p className="text-[11px] font-semibold text-amber-600 mt-1 flex items-center gap-1">
                    <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                      warning
                    </span>
                    {warning}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={clearSelectedSeller}
                disabled={submitting}
                className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-line hover:bg-surface text-[11px] font-bold text-ink transition-colors cursor-pointer disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Change
              </button>
            </div>
          ) : canListSellers ? (
            <div className="relative">
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
                  placeholder="Search by business name, username, or email…"
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
                    <p className="px-3 py-3 text-xs text-ink-muted">No sellers match that search.</p>
                  ) : (
                    <ul>
                      {searchResults.map((row) => {
                        const rowWarning = eligibilityWarning(row);
                        return (
                          <li key={row.id}>
                            <button
                              type="button"
                              onClick={() => selectSeller(row)}
                              className="w-full text-left px-3 py-2.5 hover:bg-surface-alt transition-colors cursor-pointer border-b border-line last:border-0"
                            >
                              <p className="text-xs font-bold text-ink flex items-center gap-1.5">
                                {row.business_name}
                                {rowWarning && (
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-600">
                                    Ineligible
                                  </span>
                                )}
                              </p>
                              <p className="text-[11px] text-ink-muted">
                                {row.username} &middot; {row.seller_type} &middot; {row.status}
                              </p>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}
              <p className="text-[10px] text-ink-faint mt-1">
                Start typing to search the seller directory. Only an existing, eligible seller
                can be assigned as owner — the backend re-validates eligibility regardless of
                what is shown here.
              </p>
            </div>
          ) : (
            <div>
              <input
                type="number"
                min={1}
                value={manualSellerId}
                onChange={(e) => setManualSellerId(e.target.value)}
                disabled={submitting}
                placeholder="Seller (SellerProfile) ID"
                className={FIELD_CONTROL_CLASS}
              />
              <p className="text-[10px] text-ink-faint mt-1">
                You don&apos;t hold <code className="font-mono">sellers.view</code>, so the
                seller directory can&apos;t be searched here — enter the numeric seller ID
                directly. The backend still validates it exists and is eligible.
              </p>
            </div>
          )}
        </div>

        <div>
          <label htmlFor="shop-name" className={FIELD_LABEL_CLASS}>
            Shop name <span className="text-red-600">*</span>
          </label>
          <input
            id="shop-name"
            type="text"
            required
            disabled={submitting}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Star Gadgets"
            className={FIELD_CONTROL_CLASS}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="shop-phone" className={FIELD_LABEL_CLASS}>
              Phone
            </label>
            <input
              id="shop-phone"
              type="text"
              disabled={submitting}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+880 1700 000000"
              className={FIELD_CONTROL_CLASS}
            />
          </div>
          <div>
            <label htmlFor="shop-address" className={FIELD_LABEL_CLASS}>
              Address
            </label>
            <input
              id="shop-address"
              type="text"
              disabled={submitting}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="12/A Motijheel, Dhaka"
              className={FIELD_CONTROL_CLASS}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="shop-latitude" className={FIELD_LABEL_CLASS}>
              Latitude
            </label>
            <input
              id="shop-latitude"
              type="number"
              step="any"
              disabled={submitting}
              value={latitude}
              onChange={(e) => setLatitude(e.target.value)}
              placeholder="23.8103"
              className={FIELD_CONTROL_CLASS}
            />
          </div>
          <div>
            <label htmlFor="shop-longitude" className={FIELD_LABEL_CLASS}>
              Longitude
            </label>
            <input
              id="shop-longitude"
              type="number"
              step="any"
              disabled={submitting}
              value={longitude}
              onChange={(e) => setLongitude(e.target.value)}
              placeholder="90.4125"
              className={FIELD_CONTROL_CLASS}
            />
          </div>
        </div>
        <div className="-mt-2 flex flex-wrap items-start justify-between gap-2">
          <UseCurrentLocationButton
            disabled={submitting}
            onLocated={(position) => {
              setLatitude(String(position.latitude));
              setLongitude(String(position.longitude));
            }}
          />
          <CoordinateMapLink latitude={latitude} longitude={longitude} />
        </div>
        {!latLngBothOrNeither && (
          <p className="text-[11px] font-semibold text-red-600">
            Provide both latitude and longitude together, or leave both blank.
          </p>
        )}

        <div>
          <label htmlFor="shop-description" className={FIELD_LABEL_CLASS}>
            Description
          </label>
          <textarea
            id="shop-description"
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
            Create shop
          </button>
          <button
            type="button"
            onClick={() => router.push("/admin/shops")}
            disabled={submitting}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Cancel
          </button>
        </div>
      </div>

      <AdminConfirmModal
        open={confirming}
        title="Create Shop"
        message={
          <>
            Create shop <strong>{name}</strong> and assign{" "}
            <strong>
              {selectedSeller ? selectedSeller.business_name : `seller #${resolvedSellerId}`}
            </strong>{" "}
            as its owner?
            <span className="block mt-2 text-ink-muted">
              The shop is created in DRAFT status. It is not automatically approved or
              activated.
            </span>
            {error && <span className="block mt-2 font-semibold text-red-600">{error}</span>}
          </>
        }
        confirmLabel="Create shop"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why this shop is being created…"
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
