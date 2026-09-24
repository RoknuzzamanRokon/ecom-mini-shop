"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  getSellerShops,
  updateSellerShop,
  submitSellerShopForReview,
  formatImageUrl,
} from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { SellerShop } from "@/lib/types";
import UseCurrentLocationButton, {
  CoordinateMapLink,
} from "@/components/location/UseCurrentLocationButton";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

interface EditFormState {
  name: string;
  description: string;
  phone: string;
  address: string;
  latitude: string;
  longitude: string;
}

export default function SellerShopsPage() {
  const [shops, setShops] = useState<SellerShop[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [editingShop, setEditingShop] = useState<SellerShop | null>(null);
  const [submittingModal, setSubmittingModal] = useState(false);

  const [formData, setFormData] = useState<EditFormState>({
    name: "",
    description: "",
    phone: "",
    address: "",
    latitude: "",
    longitude: "",
  });

  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);

  const fetchShops = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setLoadError("No active session token was found. Please sign in again.");
      return;
    }

    try {
      setLoading(true);
      setLoadError(null);
      const data = await getSellerShops(token);
      setShops(data);
    } catch (err: any) {
      setShops([]);
      setLoadError(err?.message || "Failed to load your shops. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchShops();
  }, [fetchShops]);

  const revokePreviews = useCallback(() => {
    if (logoPreview) URL.revokeObjectURL(logoPreview);
    if (coverPreview) URL.revokeObjectURL(coverPreview);
  }, [logoPreview, coverPreview]);

  const closeEditModal = useCallback(() => {
    revokePreviews();
    setEditingShop(null);
    setLogoFile(null);
    setLogoPreview(null);
    setCoverFile(null);
    setCoverPreview(null);
    setImageError(null);
  }, [revokePreviews]);

  const handleOpenEdit = (shop: SellerShop) => {
    setEditingShop(shop);
    setFormData({
      name: shop.name || "",
      description: shop.description || "",
      phone: shop.phone || "",
      address: shop.address || "",
      latitude: shop.latitude ? shop.latitude.toString() : "",
      longitude: shop.longitude ? shop.longitude.toString() : "",
    });
    setLogoFile(null);
    setLogoPreview(null);
    setCoverFile(null);
    setCoverPreview(null);
    setImageError(null);
    setActionError(null);
    setActionSuccess(null);
  };

  const validateImageFile = (file: File): string | null => {
    if (!file.type.startsWith("image/")) return "Please choose an image file.";
    if (file.size > MAX_IMAGE_BYTES) return "Image must be smaller than 5 MB.";
    return null;
  };

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const validationError = validateImageFile(file);
    if (validationError) {
      setImageError(validationError);
      if (logoInputRef.current) logoInputRef.current.value = "";
      return;
    }
    setImageError(null);
    if (logoPreview) URL.revokeObjectURL(logoPreview);
    setLogoFile(file);
    setLogoPreview(URL.createObjectURL(file));
  };

  const handleCoverChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const validationError = validateImageFile(file);
    if (validationError) {
      setImageError(validationError);
      if (coverInputRef.current) coverInputRef.current.value = "";
      return;
    }
    setImageError(null);
    if (coverPreview) URL.revokeObjectURL(coverPreview);
    setCoverFile(file);
    setCoverPreview(URL.createObjectURL(file));
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingShop) return;
    const token = getAuthToken();
    if (!token) {
      setActionError("No active session token was found. Please sign in again.");
      return;
    }

    setSubmittingModal(true);
    setActionError(null);

    try {
      const payload = new FormData();
      payload.append("name", formData.name);
      payload.append("description", formData.description);
      payload.append("phone", formData.phone);
      payload.append("address", formData.address);
      if (formData.latitude && formData.longitude) {
        payload.append("latitude", formData.latitude);
        payload.append("longitude", formData.longitude);
      }
      if (logoFile) payload.append("logo", logoFile);
      if (coverFile) payload.append("cover_image", coverFile);

      await updateSellerShop(token, editingShop.id, payload);
      setActionSuccess(`Shop "${formData.name}" updated successfully.`);
      closeEditModal();
      await fetchShops();
    } catch (err: any) {
      setActionError(err?.message || "Failed to update shop.");
    } finally {
      setSubmittingModal(false);
    }
  };

  const handleSubmitForReview = async (shop: SellerShop) => {
    const token = getAuthToken();
    if (!token) {
      setActionError("No active session token was found. Please sign in again.");
      return;
    }

    try {
      const res = await submitSellerShopForReview(token, shop.id);
      setActionSuccess(res.message || `Shop "${shop.name}" submitted for staff review.`);
      await fetchShops();
    } catch (err: any) {
      setActionError(err?.message || "Failed to submit shop for review.");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">My Shops</h1>
        <p className="text-xs text-ink-muted mt-1">
          View and manage the shop(s) assigned to your account.
        </p>
      </div>

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>{actionSuccess}</span>
        </div>
      )}

      {actionError && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{actionError}</span>
        </div>
      )}

      {/* Shop Cards Grid */}
      {loading ? (
        <div className="py-12 text-center text-xs text-ink-muted">Loading your shops...</div>
      ) : loadError ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[54px] text-accent/60 mb-3 block">
            error
          </span>
          <h3 className="text-base font-bold text-ink">Could not load your shops</h3>
          <p className="text-xs text-ink-muted max-w-sm mx-auto mt-1 mb-6">{loadError}</p>
          <button
            type="button"
            onClick={fetchShops}
            className="px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm inline-flex items-center gap-2 cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
            <span>Retry</span>
          </button>
        </div>
      ) : shops.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[54px] text-ink-muted/40 mb-3 block">
            storefront
          </span>
          <h3 className="text-base font-bold text-ink">No Shop Assigned</h3>
          <p className="text-xs text-ink-muted max-w-sm mx-auto mt-1">
            No shop has been assigned to your account yet. Please contact an authorized
            administrator.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {shops.map((shop) => {
            const logoUrl = formatImageUrl(shop.logo);
            const canSubmit = shop.status === "DRAFT" || shop.status === "REJECTED";

            return (
              <div
                key={shop.id}
                className="bg-surface rounded-2xl border border-line p-5 shadow-xs flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start gap-4 mb-4">
                    <div className="w-16 h-16 rounded-xl overflow-hidden bg-surface-alt border border-line shrink-0 relative">
                      <Image
                        src={logoUrl}
                        alt={shop.name}
                        fill
                        className="object-cover"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-base font-bold text-ink truncate">
                          {shop.name}
                        </h3>
                        <span
                          className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded border shrink-0 ${
                            shop.status === "APPROVED" || shop.status === "ACTIVE"
                              ? "bg-success/15 text-success border-success/20"
                              : shop.status === "PENDING"
                              ? "bg-primary/15 text-primary border-primary/20"
                              : "bg-accent/15 text-accent border-accent/20"
                          }`}
                        >
                          {shop.status_display || shop.status}
                        </span>
                      </div>
                      <p className="text-xs text-ink-muted mt-0.5 truncate font-mono">
                        /shop/{shop.slug}
                      </p>
                      {shop.phone && (
                        <p className="text-xs text-ink-body mt-1 flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px] text-ink-muted">
                            phone
                          </span>
                          <span>{shop.phone}</span>
                        </p>
                      )}
                    </div>
                  </div>

                  {shop.description && (
                    <p className="text-xs text-ink-body line-clamp-2 mb-3">
                      {shop.description}
                    </p>
                  )}

                  {shop.address && (
                    <p className="text-xs text-ink-muted flex items-start gap-1 mb-3">
                      <span className="material-symbols-outlined text-[15px] shrink-0">
                        location_on
                      </span>
                      <span className="line-clamp-1">{shop.address}</span>
                    </p>
                  )}

                  {shop.rejection_reason && (
                    <div className="p-3 rounded-lg bg-accent/10 border border-accent/20 text-accent text-xs mb-3">
                      <strong>Rejection Note:</strong> {shop.rejection_reason}
                    </div>
                  )}

                  {shop.suspension_reason && (
                    <div className="p-3 rounded-lg bg-accent/10 border border-accent/20 text-accent text-xs mb-3">
                      <strong>Suspension Note:</strong> {shop.suspension_reason}
                    </div>
                  )}
                </div>

                <div className="pt-4 border-t border-line flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleOpenEdit(shop)}
                      className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-xs transition-colors cursor-pointer"
                    >
                      Manage Shop
                    </button>
                    {canSubmit && (
                      <button
                        type="button"
                        onClick={() => handleSubmitForReview(shop)}
                        className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-semibold text-xs transition-colors cursor-pointer"
                      >
                        Submit for Review
                      </button>
                    )}
                  </div>

                  <Link
                    href={`/shop/${shop.slug}`}
                    target="_blank"
                    className="text-xs font-semibold text-primary hover:underline inline-flex items-center gap-1"
                  >
                    <span>View Public Shop</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_outward</span>
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Edit Shop Modal */}
      {editingShop && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-lg w-full p-6 space-y-4 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <h3 className="text-base font-bold text-ink">Manage Shop: {editingShop.name}</h3>
              <button
                type="button"
                onClick={closeEditModal}
                className="text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="space-y-4">
              {/* Logo & Cover Image */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">Logo</label>
                  <div className="flex items-center gap-2">
                    <div className="w-14 h-14 rounded-lg overflow-hidden bg-surface-alt border border-line shrink-0 relative">
                      <Image
                        src={logoPreview || formatImageUrl(editingShop.logo)}
                        alt="Shop logo"
                        fill
                        className="object-cover"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <input
                        ref={logoInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleLogoChange}
                        className="hidden"
                      />
                      <button
                        type="button"
                        onClick={() => logoInputRef.current?.click()}
                        className="px-2.5 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-[11px] transition-colors cursor-pointer"
                      >
                        {logoPreview ? "Replace" : "Change"}
                      </button>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Cover Image
                  </label>
                  <div className="flex items-center gap-2">
                    <div className="w-14 h-14 rounded-lg overflow-hidden bg-surface-alt border border-line shrink-0 relative">
                      <Image
                        src={coverPreview || formatImageUrl(editingShop.cover_image)}
                        alt="Shop cover"
                        fill
                        className="object-cover"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <input
                        ref={coverInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleCoverChange}
                        className="hidden"
                      />
                      <button
                        type="button"
                        onClick={() => coverInputRef.current?.click()}
                        className="px-2.5 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-[11px] transition-colors cursor-pointer"
                      >
                        {coverPreview ? "Replace" : "Change"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              {imageError && (
                <p className="text-[11px] font-semibold text-accent">{imageError}</p>
              )}
              <p className="text-[10px] text-ink-faint -mt-2">JPG or PNG, up to 5 MB.</p>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Shop Name <span className="text-accent">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Star Gadgets"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Phone Number
                </label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="+880 1700 000000"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Street Address
                </label>
                <input
                  type="text"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="e.g. 12/A Motijheel, Dhaka"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="seller-shop-latitude" className="block text-xs font-semibold text-ink mb-1.5">
                    Latitude
                  </label>
                  <input
                    id="seller-shop-latitude"
                    type="number"
                    step="any"
                    value={formData.latitude}
                    onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                    placeholder="23.8103"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label htmlFor="seller-shop-longitude" className="block text-xs font-semibold text-ink mb-1.5">
                    Longitude
                  </label>
                  <input
                    id="seller-shop-longitude"
                    type="number"
                    step="any"
                    value={formData.longitude}
                    onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                    placeholder="90.4125"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>
              </div>
              <div className="-mt-1 flex flex-wrap items-start justify-between gap-2">
                <UseCurrentLocationButton
                  disabled={submittingModal}
                  onLocated={(position) =>
                    setFormData((prev) => ({
                      ...prev,
                      latitude: String(position.latitude),
                      longitude: String(position.longitude),
                    }))
                  }
                />
                <CoordinateMapLink latitude={formData.latitude} longitude={formData.longitude} />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Tell customers about your shop..."
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-line">
                <button
                  type="button"
                  onClick={closeEditModal}
                  className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingModal}
                  className="px-5 py-2 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-all flex items-center gap-2 cursor-pointer"
                >
                  {submittingModal ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
