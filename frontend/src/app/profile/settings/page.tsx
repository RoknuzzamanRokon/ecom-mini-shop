"use client";

import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useProfile } from "@/context/ProfileContext";
import {
  changePassword,
  formatImageUrl,
  updateCustomerProfile,
  uploadAvatar,
} from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

type Banner = { type: "success" | "error"; text: string } | null;

const GENDERS = [
  { value: "", label: "Not specified" },
  { value: "MALE", label: "Male" },
  { value: "FEMALE", label: "Female" },
  { value: "OTHER", label: "Other" },
  { value: "PREFER_NOT_TO_SAY", label: "Prefer not to say" },
];

export default function ProfileSettingsPage() {
  const { profile, setProfile, refreshProfile } = useProfile();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [details, setDetails] = useState({
    first_name: "",
    last_name: "",
    display_name: "",
    phone: "",
    date_of_birth: "",
    gender: "",
  });
  const [detailsBanner, setDetailsBanner] = useState<Banner>(null);
  const [savingDetails, setSavingDetails] = useState(false);

  const [avatarBanner, setAvatarBanner] = useState<Banner>(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const [passwords, setPasswords] = useState({
    current_password: "",
    new_password: "",
    new_password_confirm: "",
  });
  const [passwordBanner, setPasswordBanner] = useState<Banner>(null);
  const [savingPassword, setSavingPassword] = useState(false);

  useEffect(() => {
    if (profile) {
      setDetails({
        first_name: profile.first_name || "",
        last_name: profile.last_name || "",
        display_name: profile.display_name || "",
        phone: profile.phone || "",
        date_of_birth: profile.date_of_birth || "",
        gender: profile.gender || "",
      });
    }
  }, [profile]);

  const handleDetailsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;

    setSavingDetails(true);
    setDetailsBanner(null);
    try {
      const payload: Record<string, string | null> = { ...details };
      // The API rejects an empty string for an optional date.
      if (!payload.date_of_birth) payload.date_of_birth = null;
      const updated = await updateCustomerProfile(payload, token);
      setProfile(updated);
      setDetailsBanner({ type: "success", text: "Profile details saved." });
    } catch {
      setDetailsBanner({ type: "error", text: "Could not save your details." });
    } finally {
      setSavingDetails(false);
    }
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const token = getAuthToken();
    if (!token) return;

    setUploadingAvatar(true);
    setAvatarBanner(null);
    try {
      const updated = await uploadAvatar(file, token);
      setProfile(updated);
      setAvatarBanner({ type: "success", text: "Photo updated." });
    } catch {
      setAvatarBanner({ type: "error", text: "Could not upload that photo." });
    } finally {
      setUploadingAvatar(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;

    setSavingPassword(true);
    setPasswordBanner(null);
    try {
      await changePassword(passwords, token);
      setPasswords({
        current_password: "",
        new_password: "",
        new_password_confirm: "",
      });
      setPasswordBanner({ type: "success", text: "Password changed." });
    } catch (err) {
      setPasswordBanner({
        type: "error",
        text: err instanceof Error ? err.message : "Could not change password.",
      });
    } finally {
      setSavingPassword(false);
    }
  };

  const inputClass =
    "w-full px-3 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors";
  const labelClass = "block text-xs font-semibold text-ink-body mb-1.5";

  return (
    <div className="flex flex-col gap-6">
      {/* Profile photo */}
      <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
        <h2 className="text-lg font-bold text-ink mb-1">Profile Photo</h2>
        <p className="text-xs text-ink-muted mb-4">
          Upload a picture so your account is easy to recognise.
        </p>

        <div className="flex items-center gap-5 flex-wrap">
          <div className="w-24 h-24 rounded-full overflow-hidden bg-surface-alt border border-line flex items-center justify-center shrink-0">
            {profile?.avatar ? (
              <Image
                src={formatImageUrl(profile.avatar)}
                alt="Profile photo"
                width={96}
                height={96}
                className="object-cover w-full h-full"
              />
            ) : (
              <span className="material-symbols-outlined text-[40px] text-ink-muted">
                person
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleAvatarChange}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingAvatar}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-5 py-2.5 rounded-lg shadow-sm transition-colors disabled:opacity-60 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">upload</span>
              {uploadingAvatar ? "Uploading…" : "Change Photo"}
            </button>
            <span className="text-[11px] text-ink-muted">JPG or PNG.</span>
          </div>
        </div>

        {avatarBanner && (
          <p
            className={`mt-3 text-xs font-medium ${
              avatarBanner.type === "success" ? "text-success" : "text-accent"
            }`}
          >
            {avatarBanner.text}
          </p>
        )}
      </section>

      {/* Personal details */}
      <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
        <h2 className="text-lg font-bold text-ink mb-1">Personal Details</h2>
        <p className="text-xs text-ink-muted mb-4">
          This information is used on your orders and deliveries.
        </p>

        <form onSubmit={handleDetailsSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelClass} htmlFor="first_name">First Name</label>
            <input
              id="first_name"
              className={inputClass}
              value={details.first_name}
              onChange={(e) => setDetails({ ...details, first_name: e.target.value })}
              disabled={savingDetails}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="last_name">Last Name</label>
            <input
              id="last_name"
              className={inputClass}
              value={details.last_name}
              onChange={(e) => setDetails({ ...details, last_name: e.target.value })}
              disabled={savingDetails}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="display_name">Display Name</label>
            <input
              id="display_name"
              className={inputClass}
              value={details.display_name}
              onChange={(e) => setDetails({ ...details, display_name: e.target.value })}
              disabled={savingDetails}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="phone">Phone</label>
            <input
              id="phone"
              className={inputClass}
              value={details.phone}
              onChange={(e) => setDetails({ ...details, phone: e.target.value })}
              placeholder="+880 17xx-xxxxxx"
              disabled={savingDetails}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="date_of_birth">Date of Birth</label>
            <input
              id="date_of_birth"
              type="date"
              className={inputClass}
              value={details.date_of_birth}
              onChange={(e) => setDetails({ ...details, date_of_birth: e.target.value })}
              disabled={savingDetails}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="gender">Gender</label>
            <select
              id="gender"
              className={inputClass}
              value={details.gender}
              onChange={(e) => setDetails({ ...details, gender: e.target.value })}
              disabled={savingDetails}
            >
              {GENDERS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>

          <div className="sm:col-span-2 flex items-center gap-4 flex-wrap">
            <button
              type="submit"
              disabled={savingDetails}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors disabled:opacity-60 cursor-pointer"
            >
              {savingDetails ? "Saving…" : "Save Changes"}
            </button>
            {detailsBanner && (
              <span
                className={`text-xs font-medium ${
                  detailsBanner.type === "success" ? "text-success" : "text-accent"
                }`}
              >
                {detailsBanner.text}
              </span>
            )}
          </div>
        </form>
      </section>

      {/* Password */}
      <section className="bg-surface rounded-2xl border border-line shadow-sm p-6">
        <h2 className="text-lg font-bold text-ink mb-1">Change Password</h2>
        <p className="text-xs text-ink-muted mb-4">
          Minimum 4 characters. You will stay signed in on this device.
        </p>

        <form onSubmit={handlePasswordSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="current_password">Current Password</label>
            <input
              id="current_password"
              type="password"
              autoComplete="current-password"
              className={inputClass}
              value={passwords.current_password}
              onChange={(e) =>
                setPasswords({ ...passwords, current_password: e.target.value })
              }
              disabled={savingPassword}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="new_password">New Password</label>
            <input
              id="new_password"
              type="password"
              autoComplete="new-password"
              className={inputClass}
              value={passwords.new_password}
              onChange={(e) =>
                setPasswords({ ...passwords, new_password: e.target.value })
              }
              disabled={savingPassword}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="new_password_confirm">Confirm New Password</label>
            <input
              id="new_password_confirm"
              type="password"
              autoComplete="new-password"
              className={inputClass}
              value={passwords.new_password_confirm}
              onChange={(e) =>
                setPasswords({ ...passwords, new_password_confirm: e.target.value })
              }
              disabled={savingPassword}
              required
            />
          </div>

          <div className="sm:col-span-2 flex items-center gap-4 flex-wrap">
            <button
              type="submit"
              disabled={savingPassword}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors disabled:opacity-60 cursor-pointer"
            >
              {savingPassword ? "Updating…" : "Update Password"}
            </button>
            {passwordBanner && (
              <span
                className={`text-xs font-medium ${
                  passwordBanner.type === "success" ? "text-success" : "text-accent"
                }`}
              >
                {passwordBanner.text}
              </span>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}
