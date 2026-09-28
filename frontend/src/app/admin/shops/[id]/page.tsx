"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import {
  AdminApiError,
  AdminShop,
  AdminShopUpdatePayload,
  getAdminShopDetail,
  updateAdminShop,
} from "@/lib/admin-api";
import { formatDateTime, humanizeToken } from "@/lib/admin-format";
import { AdminConfirmModal, AdminStatusBadge } from "@/components/admin/shared";
import UseCurrentLocationButton, {
  CoordinateMapLink,
} from "@/components/location/UseCurrentLocationButton";
import {
  SHOP_STATUS_LABELS,
  ShopPhoneListField,
  canUpdateAdminShops,
  getAvailableShopActions,
  rowsToShopPhones,
  shopPhonesToRows,
  useShopStatusAction,
} from "../shopGovernance";

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-2";

/** AdminShopUpdateSerializer's text fields; phone numbers and location are handled separately. */
const EDITABLE_SHOP_FIELDS = ["name", "address", "description"] as const;

type ShopTextField = (typeof EDITABLE_SHOP_FIELDS)[number];

interface ShopDetailsForm extends Pick<AdminShop, ShopTextField> {
  /** Row 0 is the main number. */
  phoneRows: string[];
  latitude: string;
  longitude: string;
}

function toDetailsForm(shop: AdminShop): ShopDetailsForm {
  return {
    name: shop.name,
    address: shop.address,
    description: shop.description,
    phoneRows: shopPhonesToRows(shop),
    latitude: shop.latitude != null ? String(shop.latitude) : "",
    longitude: shop.longitude != null ? String(shop.longitude) : "",
  };
}

function samePhones(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((phone, i) => phone === b[i]);
}

const ACTION_BUTTON_TONE: Record<string, string> = {
  primary:
    "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary",
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
    <div className="space-y-6" aria-busy="true" aria-label="Loading shop detail">
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

export default function AdminShopDetailPage() {
  const params = useParams<{ id: string }>();
  const shopId = params.id;
  const { user } = useAuth();

  const [shop, setShop] = useState<AdminShop | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchShop = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminShopDetail(token, shopId);
      setShop(data);
    } catch (err) {
      setShop(null);
      setError(err instanceof Error ? err : new Error("Failed to load shop."));
    } finally {
      setLoading(false);
    }
  }, [shopId]);

  useEffect(() => {
    fetchShop();
  }, [fetchShop]);

  const handleActionSuccess = useCallback((updated: AdminShop) => {
    setShop(updated);
  }, []);
  const { pendingAction, targetShop, submitError, requestAction, cancel, confirm } =
    useShopStatusAction(handleActionSuccess);

  // ---------------------------------------------------------------------------
  // Shop details edit (shops.update)
  // ---------------------------------------------------------------------------

  const canUpdate = canUpdateAdminShops(user);
  /** Non-null while the edit form is open. */
  const [editValues, setEditValues] = useState<ShopDetailsForm | null>(null);
  const [confirmingEdit, setConfirmingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [detailsNotice, setDetailsNotice] = useState<string | null>(null);

  const startEditing = useCallback(() => {
    if (!shop) return;
    setEditValues(toDetailsForm(shop));
    setEditError(null);
    setDetailsNotice(null);
  }, [shop]);

  const cancelEditing = useCallback(() => {
    setEditValues(null);
    setConfirmingEdit(false);
    setEditError(null);
  }, []);

  const latText = editValues?.latitude.trim() ?? "";
  const lngText = editValues?.longitude.trim() ?? "";
  const latLngBothOrNeither = (latText === "") === (lngText === "");

  // Only what differs from the loaded shop, trimmed the way DRF trims it, so the
  // audit log records real changes only. Location is sent as a pair, and an
  // emptied pair is sent as null/null, which clears it.
  const changedDetails = useMemo(() => {
    const changes: Omit<AdminShopUpdatePayload, "reason"> = {};
    if (!shop || !editValues) return changes;
    for (const field of EDITABLE_SHOP_FIELDS) {
      const value = editValues[field].trim();
      if (value !== shop[field]) changes[field] = value;
    }
    // Sent as a pair: the backend drops an extra number that equals the main one.
    const phones = rowsToShopPhones(editValues.phoneRows);
    if (
      phones.phone !== shop.phone ||
      !samePhones(phones.additional_phones, shop.additional_phones ?? [])
    ) {
      changes.phone = phones.phone;
      changes.additional_phones = phones.additional_phones;
    }
    if (latLngBothOrNeither) {
      const lat = latText === "" ? null : Number(latText);
      const lng = lngText === "" ? null : Number(lngText);
      if (lat !== shop.latitude || lng !== shop.longitude) {
        changes.latitude = lat;
        changes.longitude = lng;
      }
    }
    return changes;
  }, [shop, editValues, latText, lngText, latLngBothOrNeither]);
  const changedLabels = Object.keys(changedDetails)
    .filter((field) => field !== "longitude" && field !== "additional_phones")
    .map((field) =>
      field === "latitude" ? "Location" : field === "phone" ? "Phone numbers" : humanizeToken(field)
    );
  const hasDetailChanges = changedLabels.length > 0;
  const editNameValid = Boolean(editValues?.name.trim());
  const canSaveEdit = hasDetailChanges && editNameValid && latLngBothOrNeither;

  const confirmEdit = useCallback(
    async (reason: string) => {
      if (!shop || !hasDetailChanges) return;
      const token = getAuthToken();
      if (!token) {
        setEditError("No active session token was found. Please sign in again.");
        return;
      }
      try {
        setEditError(null);
        // The PATCH response is authoritative; render it, not what was typed.
        const updated = await updateAdminShop(token, shop.id, { ...changedDetails, reason });
        setShop(updated);
        setEditValues(null);
        setConfirmingEdit(false);
        setDetailsNotice("Shop details updated.");
      } catch (err) {
        setEditError(err instanceof AdminApiError ? err.message : "Failed to update shop details.");
      }
    },
    [shop, hasDetailChanges, changedDetails]
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

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !shop) {
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
              {isNotFound ? "Shop not found" : "Unable to load shop"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This shop does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchShop}
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

  const availableActions = getAvailableShopActions(shop, user);

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {shop.name}
              </h1>
              <AdminStatusBadge status={shop.status} label={SHOP_STATUS_LABELS[shop.status]} />
            </div>
            <p className="text-xs text-ink-muted mt-1">/{shop.slug}</p>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                inventory_2
              </span>
              {shop.products_count} product{shop.products_count === 1 ? "" : "s"}
            </p>
          </div>

          {(availableActions.length > 0 || canUpdate) && (
            <div className="flex flex-wrap gap-2 shrink-0">
              {canUpdate && !editValues && (
                <button
                  type="button"
                  onClick={startEditing}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors shadow-xs cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 ${ACTION_BUTTON_TONE.default}`}
                >
                  <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                    edit
                  </span>
                  Edit details
                </button>
              )}
              {availableActions.map((descriptor) => (
                <button
                  key={descriptor.action}
                  type="button"
                  onClick={() => requestAction(shop, descriptor)}
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

        {shop.description && (
          <p className="text-xs text-ink-muted leading-relaxed mt-4 pt-4 border-t border-line whitespace-pre-line">
            {shop.description}
          </p>
        )}
      </div>

      {detailsNotice && (
        <div
          role="status"
          className="rounded-xl border border-success/30 bg-success/10 p-3 flex items-start gap-2"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-success shrink-0">
            check_circle
          </span>
          <p className="text-xs font-semibold text-success">{detailsNotice}</p>
        </div>
      )}

      {editValues && (
        <section
          aria-label="Edit shop details"
          className="bg-surface rounded-2xl border border-line shadow-xs p-4 sm:p-6"
        >
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider">
            Edit Shop Details
          </h2>
          <p className="text-xs text-ink-muted mt-1 mb-4">
            Owner, status and the public URL (/{shop.slug}) are not editable here. Status only
            changes through the lifecycle actions above.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canSaveEdit) return;
              setEditError(null);
              setConfirmingEdit(true);
            }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="edit-shop-name" className={FIELD_LABEL_CLASS}>
                  Shop name <span className="text-danger">*</span>
                </label>
                <input
                  id="edit-shop-name"
                  type="text"
                  required
                  maxLength={200}
                  value={editValues.name}
                  onChange={(e) => setEditValues({ ...editValues, name: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              </div>
              <ShopPhoneListField
                idPrefix="edit-shop-phone"
                rows={editValues.phoneRows}
                onChange={(phoneRows) => setEditValues({ ...editValues, phoneRows })}
              />
            </div>
            <div>
              <label htmlFor="edit-shop-address" className={FIELD_LABEL_CLASS}>
                Address
              </label>
              <input
                id="edit-shop-address"
                type="text"
                value={editValues.address}
                onChange={(e) => setEditValues({ ...editValues, address: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="edit-shop-latitude" className={FIELD_LABEL_CLASS}>
                  Latitude
                </label>
                <input
                  id="edit-shop-latitude"
                  type="number"
                  step="any"
                  value={editValues.latitude}
                  onChange={(e) => setEditValues({ ...editValues, latitude: e.target.value })}
                  placeholder="23.8103"
                  className={FIELD_CONTROL_CLASS}
                />
              </div>
              <div>
                <label htmlFor="edit-shop-longitude" className={FIELD_LABEL_CLASS}>
                  Longitude
                </label>
                <input
                  id="edit-shop-longitude"
                  type="number"
                  step="any"
                  value={editValues.longitude}
                  onChange={(e) => setEditValues({ ...editValues, longitude: e.target.value })}
                  placeholder="90.4125"
                  className={FIELD_CONTROL_CLASS}
                />
              </div>
            </div>
            <div className="-mt-2 flex flex-wrap items-start justify-between gap-2">
              <UseCurrentLocationButton
                onLocated={(position) =>
                  setEditValues({
                    ...editValues,
                    latitude: String(position.latitude),
                    longitude: String(position.longitude),
                  })
                }
              />
              <CoordinateMapLink latitude={editValues.latitude} longitude={editValues.longitude} />
            </div>
            <p className={`text-[11px] ${latLngBothOrNeither ? "text-ink-faint" : "font-semibold text-danger"}`}>
              Provide both latitude and longitude together. Clearing both removes the location, and
              the shop stops appearing in nearby-shop search.
            </p>
            <div>
              <label htmlFor="edit-shop-description" className={FIELD_LABEL_CLASS}>
                Description
              </label>
              <textarea
                id="edit-shop-description"
                rows={3}
                value={editValues.description}
                onChange={(e) => setEditValues({ ...editValues, description: e.target.value })}
                className={`${FIELD_CONTROL_CLASS} resize-y`}
              />
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="submit"
                disabled={!canSaveEdit}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Save changes
              </button>
              <button
                type="button"
                onClick={cancelEditing}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-line hover:bg-surface-alt text-xs font-bold text-ink transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Owner */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">Owner</h2>
          <dl>
            <InfoRow label="Business Name" value={shop.owner_business_name || "—"} />
            <InfoRow label="Seller ID" value={shop.owner_id} />
          </dl>
        </div>

        {/* Contact & Location */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Contact &amp; Location
          </h2>
          <dl>
            <InfoRow
              label="Phone"
              value={
                shop.phone || shop.additional_phones?.length ? (
                  <ul className="space-y-0.5">
                    {[shop.phone, ...(shop.additional_phones ?? [])]
                      .filter(Boolean)
                      .map((phone, index) => (
                        <li key={phone} className="flex items-baseline gap-2">
                          <a href={`tel:${phone}`} className="text-ink hover:text-primary hover:underline">
                            {phone}
                          </a>
                          {index === 0 && shop.phone && (
                            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
                              Main
                            </span>
                          )}
                        </li>
                      ))}
                  </ul>
                ) : (
                  "—"
                )
              }
            />
            <InfoRow label="Address" value={shop.address || "—"} />
            <InfoRow
              label="Coordinates"
              value={
                shop.latitude != null && shop.longitude != null ? (
                  <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-mono">
                      {shop.latitude}, {shop.longitude}
                    </span>
                    <CoordinateMapLink
                      latitude={String(shop.latitude)}
                      longitude={String(shop.longitude)}
                    />
                  </span>
                ) : (
                  <span className="text-ink-muted">
                    Not set — the shop won&apos;t appear in nearby-shop search.
                  </span>
                )
              }
            />
          </dl>
        </div>

        {/* Governance metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 lg:col-span-2">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Governance Metadata
          </h2>
          <dl>
            <InfoRow label="Created" value={formatDateTime(shop.created_at)} />
            <InfoRow label="Last Updated" value={formatDateTime(shop.updated_at)} />
            <InfoRow label="Reviewed At" value={formatDateTime(shop.reviewed_at)} />
            <InfoRow label="Approved At" value={formatDateTime(shop.approved_at)} />
            <InfoRow label="Suspended At" value={formatDateTime(shop.suspended_at)} />
            {shop.rejection_reason && (
              <InfoRow
                label="Rejection Reason"
                value={<span className="text-red-600">{shop.rejection_reason}</span>}
              />
            )}
            {shop.suspension_reason && (
              <InfoRow
                label="Suspension Reason"
                value={<span className="text-red-600">{shop.suspension_reason}</span>}
              />
            )}
          </dl>
        </div>
      </div>

      <AdminConfirmModal
        open={Boolean(pendingAction && targetShop)}
        title={pendingAction?.confirmTitle ?? ""}
        message={
          <>
            {targetShop && pendingAction ? pendingAction.confirmMessage(targetShop) : ""}
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

      <AdminConfirmModal
        open={confirmingEdit}
        title="Update Shop Details"
        message={
          <>
            Save changes to <strong>{changedLabels.join(", ")}</strong> for{" "}
            <strong>{shop.name}</strong>?
            {editError && <span className="block mt-2 font-semibold text-danger">{editError}</span>}
          </>
        }
        confirmLabel="Save changes"
        requireReason
        reasonRequired
        reasonLabel="Reason (recorded in the audit log)"
        reasonPlaceholder="Explain why these details are being changed…"
        onConfirm={confirmEdit}
        onCancel={() => {
          setConfirmingEdit(false);
          setEditError(null);
        }}
      />
    </div>
  );
}
