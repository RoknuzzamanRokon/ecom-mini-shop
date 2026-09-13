"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSeller } from "@/components/seller/SellerGuard";
import {
  getSellerShops,
  createSellerShop,
  updateSellerShop,
  submitSellerShopForReview,
  formatImageUrl,
} from "@/lib/api";
import { SellerShop } from "@/lib/types";

export default function SellerShopsPage() {
  const { seller, capabilities } = useSeller();

  const [shops, setShops] = useState<SellerShop[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingShop, setEditingShop] = useState<SellerShop | null>(null);
  const [submittingModal, setSubmittingModal] = useState(false);

  // Form inputs
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    phone: "",
    address: "",
    latitude: "",
    longitude: "",
    submit_for_review: false,
  });

  const fetchShops = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    try {
      setLoading(true);
      const data = await getSellerShops(token);
      setShops(data);
    } catch (err: any) {
      setActionError(err.message || "Failed to load shops.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchShops();
  }, [fetchShops]);

  // Seller type restrictions check
  const isProductOwner = seller?.seller_type === "PRODUCT_OWNER";
  const isLimitedOwner = seller?.seller_type === "LIMITED_SHOP_OWNER";
  const hasReachedShopLimit =
    isProductOwner || (isLimitedOwner && shops.length >= (capabilities?.max_shops || 1));

  const handleOpenCreate = () => {
    setFormData({
      name: "",
      description: "",
      phone: "",
      address: "",
      latitude: "",
      longitude: "",
      submit_for_review: false,
    });
    setActionError(null);
    setActionSuccess(null);
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (shop: SellerShop) => {
    setEditingShop(shop);
    setFormData({
      name: shop.name || "",
      description: shop.description || "",
      phone: shop.phone || "",
      address: shop.address || "",
      latitude: shop.latitude ? shop.latitude.toString() : "",
      longitude: shop.longitude ? shop.longitude.toString() : "",
      submit_for_review: false,
    });
    setActionError(null);
    setActionSuccess(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    setSubmittingModal(true);
    setActionError(null);

    try {
      const payload: Record<string, any> = {
        name: formData.name,
        description: formData.description,
        phone: formData.phone,
        address: formData.address,
        submit_for_review: formData.submit_for_review,
      };
      if (formData.latitude && formData.longitude) {
        payload.latitude = parseFloat(formData.latitude);
        payload.longitude = parseFloat(formData.longitude);
      }

      await createSellerShop(token, payload);
      setActionSuccess(`Shop "${formData.name}" created successfully.`);
      setIsCreateOpen(false);
      await fetchShops();
    } catch (err: any) {
      setActionError(err.message || "Failed to create shop.");
    } finally {
      setSubmittingModal(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingShop) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    setSubmittingModal(true);
    setActionError(null);

    try {
      const payload: Record<string, any> = {
        name: formData.name,
        description: formData.description,
        phone: formData.phone,
        address: formData.address,
      };
      if (formData.latitude && formData.longitude) {
        payload.latitude = parseFloat(formData.latitude);
        payload.longitude = parseFloat(formData.longitude);
      }

      await updateSellerShop(token, editingShop.id, payload);
      setActionSuccess(`Shop "${formData.name}" updated successfully.`);
      setEditingShop(null);
      await fetchShops();
    } catch (err: any) {
      setActionError(err.message || "Failed to update shop.");
    } finally {
      setSubmittingModal(false);
    }
  };

  const handleSubmitForReview = async (shop: SellerShop) => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    try {
      const res = await submitSellerShopForReview(token, shop.id);
      setActionSuccess(res.message || `Shop "${shop.name}" submitted for staff review.`);
      await fetchShops();
    } catch (err: any) {
      setActionError(err.message || "Failed to submit shop for review.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Shop Management
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Create, configure, and maintain your storefront presences on MiniShop.
          </p>
        </div>

        <div>
          <button
            type="button"
            onClick={handleOpenCreate}
            disabled={hasReachedShopLimit}
            className="px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm flex items-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[18px]">add_business</span>
            <span>Create New Shop</span>
          </button>
        </div>
      </div>

      {/* Seller Type Limit Notice */}
      {isProductOwner ? (
        <div className="p-3.5 rounded-xl bg-accent/10 border border-accent/20 text-accent text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] shrink-0">info</span>
          <span>
            <strong>Product Owner Tier:</strong> Your account sells products through assigned shops and cannot register independent shops.
          </span>
        </div>
      ) : isLimitedOwner && hasReachedShopLimit ? (
        <div className="p-3.5 rounded-xl bg-surface-alt border border-line text-ink-muted text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-primary shrink-0">info</span>
          <span>
            <strong>Limited Shop Owner:</strong> Maximum shop limit (1 shop) reached. Manage your existing shop below.
          </span>
        </div>
      ) : null}

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
      ) : shops.length === 0 ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[54px] text-ink-muted/40 mb-3 block">
            storefront
          </span>
          <h3 className="text-base font-bold text-ink">No Shops Registered</h3>
          <p className="text-xs text-ink-muted max-w-sm mx-auto mt-1 mb-6">
            You have not registered any shops yet. Create a shop to start listing your products on the MiniShop storefront.
          </p>
          {!hasReachedShopLimit && (
            <button
              type="button"
              onClick={handleOpenCreate}
              className="px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm inline-flex items-center gap-2 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[18px]">add_business</span>
              <span>Create Shop</span>
            </button>
          )}
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
                      Edit Shop
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

                  {shop.is_publicly_visible && (
                    <Link
                      href={`/shop/${shop.slug}`}
                      target="_blank"
                      className="text-xs font-semibold text-primary hover:underline inline-flex items-center gap-1"
                    >
                      <span>Public Store</span>
                      <span className="material-symbols-outlined text-[14px]">arrow_outward</span>
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create / Edit Shop Modal */}
      {(isCreateOpen || editingShop) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-lg w-full p-6 space-y-4 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <h3 className="text-base font-bold text-ink">
                {isCreateOpen ? "Create New Shop" : `Edit Shop: ${editingShop?.name}`}
              </h3>
              <button
                type="button"
                onClick={() => {
                  setIsCreateOpen(false);
                  setEditingShop(null);
                }}
                className="text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <form
              onSubmit={isCreateOpen ? handleCreateSubmit : handleEditSubmit}
              className="space-y-4"
            >
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
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Latitude
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={formData.latitude}
                    onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                    placeholder="23.8103"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Longitude
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={formData.longitude}
                    onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                    placeholder="90.4125"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>
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

              {isCreateOpen && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="submit_for_review"
                    checked={formData.submit_for_review}
                    onChange={(e) =>
                      setFormData({ ...formData, submit_for_review: e.target.checked })
                    }
                    className="rounded text-primary focus:ring-primary h-4 w-4"
                  />
                  <label
                    htmlFor="submit_for_review"
                    className="text-xs text-ink cursor-pointer select-none"
                  >
                    Submit directly for staff review upon creation
                  </label>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-line">
                <button
                  type="button"
                  onClick={() => {
                    setIsCreateOpen(false);
                    setEditingShop(null);
                  }}
                  className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingModal}
                  className="px-5 py-2 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-all flex items-center gap-2 cursor-pointer"
                >
                  {submittingModal ? "Saving..." : isCreateOpen ? "Create Shop" : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
