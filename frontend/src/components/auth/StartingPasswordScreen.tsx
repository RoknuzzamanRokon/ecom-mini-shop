"use client";

import React, { useState } from "react";
import { changePassword } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

interface StartingPasswordScreenProps {
  username: string;
  /** The new token pair: the account is free once it is stored and the user reloaded. */
  onChanged: (tokens: { access: string; refresh: string }) => Promise<void>;
  onSignOut: () => void;
}

const INPUT_CLASS =
  "w-full px-3 py-2.5 rounded-lg border border-line bg-surface text-ink placeholder-ink-muted text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary disabled:opacity-60 transition-colors";
const LABEL_CLASS = "block text-xs font-semibold text-ink-body mb-1.5";

/**
 * Shown instead of the whole site while the account is on the password a
 * Sales Team member set when opening it (rbac.StartingPassword): the API
 * answers nothing else until the owner chooses their own. Later changes go
 * through Settings as usual.
 */
export default function StartingPasswordScreen({ username, onChanged, onSignOut }: StartingPasswordScreenProps) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const token = getAuthToken();
    if (!token || saving) return;
    if (next !== confirm) {
      setError("The two new passwords do not match.");
      return;
    }
    setSaving(true);
    setError(null);
    changePassword({ current_password: current, new_password: next, new_password_confirm: confirm }, token)
      .then(onChanged)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Your password could not be changed.");
        setSaving(false);
      });
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-page p-4">
      <div className="w-full max-w-md bg-surface rounded-2xl border border-line shadow-sm p-6 sm:p-8">
        <span aria-hidden="true" className="material-symbols-outlined text-[36px] text-primary">
          lock_reset
        </span>
        <h1 className="text-lg font-black text-ink mt-2">Choose your own password</h1>
        <p className="text-xs text-ink-muted leading-relaxed mt-1.5">
          Welcome, {username}. The Sales Team member who opened your account set your first password, so choose one
          only you know before you continue. You can change it again later in Settings.
        </p>

        <form onSubmit={submit} className="space-y-4 mt-5">
          <div>
            <label className={LABEL_CLASS} htmlFor="starting_current_password">
              Password you signed in with
            </label>
            <input
              id="starting_current_password"
              type="password"
              autoComplete="current-password"
              className={INPUT_CLASS}
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              disabled={saving}
              required
            />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="starting_new_password">
              New password
            </label>
            <input
              id="starting_new_password"
              type="password"
              autoComplete="new-password"
              className={INPUT_CLASS}
              value={next}
              onChange={(event) => setNext(event.target.value)}
              disabled={saving}
              required
            />
            <p className="text-[11px] text-ink-muted mt-1">At least 8 characters, and different from the first one.</p>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="starting_confirm_password">
              New password again
            </label>
            <input
              id="starting_confirm_password"
              type="password"
              autoComplete="new-password"
              className={INPUT_CLASS}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              disabled={saving}
              required
            />
          </div>

          {error && (
            <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-3 rounded-lg shadow-sm transition-colors disabled:opacity-60 cursor-pointer"
          >
            {saving ? "Saving…" : "Save and continue"}
          </button>
          <button
            type="button"
            onClick={onSignOut}
            disabled={saving}
            className="w-full text-xs font-bold text-ink-muted hover:text-ink cursor-pointer"
          >
            Sign out
          </button>
        </form>
      </div>
    </main>
  );
}
