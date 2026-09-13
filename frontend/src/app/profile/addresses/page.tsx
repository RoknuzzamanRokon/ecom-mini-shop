"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Address, AddressInput } from "@/lib/types";
import {
  createCustomerAddress,
  deleteCustomerAddress,
  getCustomerAddresses,
  setDefaultCustomerAddress,
  updateCustomerAddress,
} from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

const LABELS = ["Home", "Work", "Office", "Other"];

const EMPTY_FORM: AddressInput = {
  label: "Home",
  recipient_name: "",
  phone: "",
  address_line_1: "",
  address_line_2: "",
  area: "",
  city: "",
  state: "",
  postal_code: "",
  country: "Bangladesh",
  is_default: false,
};

export default function AddressesPage() {
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<AddressInput>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    const token = getAuthToken();
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      setAddresses(await getCustomerAddresses(token));
    } catch {
      setError("We could not load your addresses. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(true);
  };

  const openEdit = (address: Address) => {
    setForm({
      label: address.label,
      recipient_name: address.recipient_name,
      phone: address.phone,
      address_line_1: address.address_line_1,
      address_line_2: address.address_line_2 || "",
      area: address.area || "",
      city: address.city,
      state: address.state || "",
      postal_code: address.postal_code,
      country: address.country,
      is_default: address.is_default,
    });
    setEditingId(address.id);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;

    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await updateCustomerAddress(editingId, form, token);
      } else {
        await createCustomerAddress(form, token);
      }
      setShowForm(false);
      setEditingId(null);
      await load();
    } catch {
      setError("Could not save the address. Check the fields and try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    const token = getAuthToken();
    if (!token) return;

    setBusyId(id);
    try {
      await deleteCustomerAddress(id, token);
      setAddresses((prev) => prev.filter((a) => a.id !== id));
    } catch {
      setError("Could not delete that address.");
    } finally {
      setBusyId(null);
    }
  };

  const handleSetDefault = async (id: number) => {
    const token = getAuthToken();
    if (!token) return;

    setBusyId(id);
    try {
      await setDefaultCustomerAddress(id, token);
      await load();
    } catch {
      setError("Could not set that address as default.");
    } finally {
      setBusyId(null);
    }
  };

  const inputClass =
    "w-full px-3 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors";
  const labelClass = "block text-xs font-semibold text-ink-body mb-1.5";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-ink">Delivery Addresses</h1>
          <p className="text-xs text-ink-muted mt-0.5">
            Where we deliver your orders.
          </p>
        </div>
        {!showForm && (
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-5 py-2.5 rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            Add Address
          </button>
        )}
      </div>

      {error && (
        <div className="bg-accent/10 border border-accent/30 rounded-xl px-4 py-3">
          <p className="text-sm text-accent font-medium">{error}</p>
        </div>
      )}

      {/* Form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-surface rounded-2xl border border-line shadow-sm p-6 grid grid-cols-1 sm:grid-cols-2 gap-4"
        >
          <h2 className="sm:col-span-2 text-base font-bold text-ink">
            {editingId ? "Edit Address" : "New Address"}
          </h2>

          <div>
            <label className={labelClass} htmlFor="label">Label</label>
            <select
              id="label"
              className={inputClass}
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              disabled={saving}
            >
              {LABELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="recipient_name">Recipient Name *</label>
            <input
              id="recipient_name"
              className={inputClass}
              value={form.recipient_name}
              onChange={(e) => setForm({ ...form, recipient_name: e.target.value })}
              disabled={saving}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="phone">Phone *</label>
            <input
              id="phone"
              className={inputClass}
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="+880 17xx-xxxxxx"
              disabled={saving}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="postal_code">Postal Code *</label>
            <input
              id="postal_code"
              className={inputClass}
              value={form.postal_code}
              onChange={(e) => setForm({ ...form, postal_code: e.target.value })}
              disabled={saving}
              required
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="address_line_1">Address Line 1 *</label>
            <input
              id="address_line_1"
              className={inputClass}
              value={form.address_line_1}
              onChange={(e) => setForm({ ...form, address_line_1: e.target.value })}
              placeholder="House, road, block"
              disabled={saving}
              required
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="address_line_2">Address Line 2</label>
            <input
              id="address_line_2"
              className={inputClass}
              value={form.address_line_2}
              onChange={(e) => setForm({ ...form, address_line_2: e.target.value })}
              disabled={saving}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="area">Area</label>
            <input
              id="area"
              className={inputClass}
              value={form.area}
              onChange={(e) => setForm({ ...form, area: e.target.value })}
              placeholder="Banani, Dhanmondi…"
              disabled={saving}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="city">City *</label>
            <input
              id="city"
              className={inputClass}
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
              disabled={saving}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="state">State / Division</label>
            <input
              id="state"
              className={inputClass}
              value={form.state}
              onChange={(e) => setForm({ ...form, state: e.target.value })}
              disabled={saving}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="country">Country</label>
            <input
              id="country"
              className={inputClass}
              value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
              disabled={saving}
            />
          </div>

          <label className="sm:col-span-2 flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              disabled={saving}
              className="w-4 h-4 accent-[var(--c-primary)]"
            />
            <span className="text-sm text-ink">Use as my default delivery address</span>
          </label>

          <div className="sm:col-span-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors disabled:opacity-60 cursor-pointer"
            >
              {saving ? "Saving…" : editingId ? "Save Changes" : "Add Address"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
              }}
              disabled={saving}
              className="text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink px-3 py-2.5 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* List */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            location_on
          </span>
          <p className="text-sm text-ink-body mt-2">Loading addresses…</p>
        </div>
      ) : addresses.length === 0 && !showForm ? (
        <div className="bg-surface rounded-2xl border border-line p-12 text-center">
          <span className="material-symbols-outlined text-[56px] text-ink-muted/40">
            location_off
          </span>
          <h2 className="text-base font-bold text-ink mt-2">No addresses saved</h2>
          <p className="text-sm text-ink-body mt-1 mb-5">
            Add a delivery address to speed up checkout.
          </p>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            Add Address
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {addresses.map((address) => (
            <div
              key={address.id}
              className={`bg-surface rounded-2xl border shadow-sm p-5 flex flex-col gap-2 ${
                address.is_default ? "border-primary" : "border-line"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-ink-body">
                  <span className="material-symbols-outlined text-[15px]">location_on</span>
                  {address.label}
                </span>
                {address.is_default && (
                  <span className="text-[10px] font-bold uppercase tracking-wide bg-primary/10 text-primary px-2.5 py-1 rounded-full">
                    Default
                  </span>
                )}
              </div>

              <p className="text-sm font-bold text-ink">{address.recipient_name}</p>
              <p className="text-xs text-ink-body leading-relaxed">
                {address.address_line_1}
                {address.address_line_2 ? `, ${address.address_line_2}` : ""}
                {address.area ? `, ${address.area}` : ""}
                <br />
                {address.city}
                {address.state ? `, ${address.state}` : ""} {address.postal_code}
                <br />
                {address.country}
              </p>
              <p className="text-xs text-ink-muted">{address.phone}</p>

              <div className="flex items-center gap-1 pt-2 mt-auto border-t border-line flex-wrap">
                <button
                  type="button"
                  onClick={() => openEdit(address)}
                  className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-primary hover:bg-surface-alt px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[14px]">edit</span>
                  Edit
                </button>
                {!address.is_default && (
                  <button
                    type="button"
                    onClick={() => handleSetDefault(address.id)}
                    disabled={busyId === address.id}
                    className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-ink-body hover:bg-surface-alt px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[14px]">star</span>
                    Set Default
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleDelete(address.id)}
                  disabled={busyId === address.id}
                  className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-accent hover:bg-accent/10 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[14px]">delete</span>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
