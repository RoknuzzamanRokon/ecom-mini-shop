"use client";

import React, { useState, useEffect } from "react";
import { useSeller } from "@/components/seller/SellerGuard";
import { updateSellerProfile } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

export default function SellerProfilePage() {
  const { seller, refreshDashboard } = useSeller();

  const [formData, setFormData] = useState({
    business_name: "",
    business_email: "",
    business_phone: "",
    tax_id: "",
    description: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (seller) {
      setFormData({
        business_name: seller.business_name || "",
        business_email: seller.business_email || "",
        business_phone: seller.business_phone || "",
        tax_id: seller.tax_id || "",
        description: seller.description || "",
      });
    }
  }, [seller]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();

    if (!token) return;

    setSubmitting(true);
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      await updateSellerProfile(token, formData);
      setSuccessMsg("Seller profile updated successfully.");
      await refreshDashboard();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to update seller profile.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
          Seller Profile
        </h1>
        <p className="text-xs text-ink-muted mt-1">
          Review your business credentials, tier classifications, and administrative statuses.
        </p>
      </div>

      {successMsg && (
        <div className="p-4 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Read-Only Administrative Attributes */}
      <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink pb-2 border-b border-line">
          Platform Registration Details
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <span className="text-ink-muted block font-medium">Seller Account Type</span>
            <span className="font-bold text-ink inline-block mt-0.5 px-2.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
              {seller?.seller_type_display || seller?.seller_type}
            </span>
          </div>

          <div>
            <span className="text-ink-muted block font-medium">Account Status</span>
            <span
              className={`font-bold inline-block mt-0.5 px-2.5 py-0.5 rounded border ${
                seller?.status === "APPROVED" || seller?.is_operational
                  ? "bg-success/15 text-success border-success/20"
                  : "bg-accent/15 text-accent border-accent/20"
              }`}
            >
              {seller?.status_display || seller?.status}
            </span>
          </div>

          <div>
            <span className="text-ink-muted block font-medium">Associated User Account</span>
            <span className="font-bold text-ink mt-0.5 block">{seller?.username} ({seller?.user_email})</span>
          </div>

          <div>
            <span className="text-ink-muted block font-medium">Operational Status</span>
            <span className="font-bold text-ink mt-0.5 block">
              {seller?.is_operational ? "Active & Authorized to Sell" : "Suspended / Non-operational"}
            </span>
          </div>

          {seller?.rejection_reason && (
            <div className="sm:col-span-2 p-3 rounded-lg bg-accent/10 border border-accent/20 text-accent text-xs">
              <strong>Rejection Notice:</strong> {seller.rejection_reason}
            </div>
          )}

          {seller?.suspension_reason && (
            <div className="sm:col-span-2 p-3 rounded-lg bg-accent/10 border border-accent/20 text-accent text-xs">
              <strong>Suspension Notice:</strong> {seller.suspension_reason}
            </div>
          )}
        </div>
      </div>

      {/* Editable Business Information Form */}
      <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs">
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink pb-2 mb-4 border-b border-line">
          Business Contact &amp; Public Information
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              Business Name <span className="text-accent">*</span>
            </label>
            <input
              type="text"
              name="business_name"
              required
              value={formData.business_name}
              onChange={handleChange}
              placeholder="e.g. Apex Tech Store"
              className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-ink mb-1.5">
                Business Email
              </label>
              <input
                type="email"
                name="business_email"
                value={formData.business_email}
                onChange={handleChange}
                placeholder="contact@business.com"
                className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink mb-1.5">
                Business Phone
              </label>
              <input
                type="tel"
                name="business_phone"
                value={formData.business_phone}
                onChange={handleChange}
                placeholder="+880 1712 345678"
                className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              Tax ID / Trade License Number
            </label>
            <input
              type="text"
              name="tax_id"
              value={formData.tax_id}
              onChange={handleChange}
              placeholder="e.g. TRAD-123456"
              className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-ink mb-1.5">
              Business Description
            </label>
            <textarea
              name="description"
              rows={3}
              value={formData.description}
              onChange={handleChange}
              placeholder="Describe your business and catalog..."
              className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
            />
          </div>

          <div className="flex justify-end pt-3 border-t border-line">
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-all flex items-center gap-2 cursor-pointer"
            >
              {submitting ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-[16px]">
                    progress_activity
                  </span>
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[16px]">save</span>
                  <span>Save Changes</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
