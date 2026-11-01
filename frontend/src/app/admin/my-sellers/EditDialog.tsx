"use client";

import React, { useId, useState } from "react";
import Dialog from "@/components/feedback/Dialog";
import { AdminApiError } from "@/lib/admin-api";
import { isSessionRequired } from "./editSession";

export type EditValues = Record<string, string | boolean>;

export interface EditField {
  name: string;
  label: string;
  kind?: "text" | "textarea" | "checkbox";
  inputMode?: "text" | "numeric" | "decimal" | "tel" | "email";
  hint?: string;
}

/** What a form turns its draft into: the changes to send, or why it cannot be sent. */
export type EditResult = { changes: object } | { error: string };

interface EditDialogProps {
  title: string;
  description: string;
  fields: EditField[];
  initial: EditValues;
  toChanges: (draft: EditValues) => EditResult;
  onSave: (changes: object) => Promise<unknown>;
  onClose: () => void;
  /** The server said the edit session is over. */
  onSessionEnded: () => void;
}

const INPUT_CLASS =
  "w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:opacity-60";

/**
 * One form for correcting a seller, a shop or a product inside an edit
 * session. Only the fields that changed are sent; mount it with a `key` per
 * record so each opening starts from the saved values.
 */
export default function EditDialog({
  title,
  description,
  fields,
  initial,
  toChanges,
  onSave,
  onClose,
  onSessionEnded,
}: EditDialogProps) {
  const [draft, setDraft] = useState<EditValues>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const fieldId = useId();

  const set = (name: string, value: string | boolean) => {
    setDraft((current) => ({ ...current, [name]: value }));
    setError(null);
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (saving) return;
    const result = toChanges(draft);
    if ("error" in result) {
      setError(result.error);
      return;
    }
    if (Object.keys(result.changes).length === 0) {
      setError("Nothing has changed.");
      return;
    }
    setSaving(true);
    setError(null);
    onSave(result.changes)
      .then(onClose)
      .catch((err: unknown) => {
        if (err instanceof AdminApiError && isSessionRequired(err.data)) onSessionEnded();
        setError(err instanceof Error ? err.message : "The changes could not be saved.");
      })
      .finally(() => setSaving(false));
  };

  return (
    <Dialog
      open
      onClose={onClose}
      dismissible={!saving}
      labelledBy={titleId}
      describedBy={descriptionId}
      placement="sheet"
      zIndexClass="z-[100]"
      className="w-full sm:max-w-lg max-h-[90vh] overflow-y-auto bg-surface border border-line rounded-t-2xl sm:rounded-2xl shadow-lg p-6"
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <h2 id={titleId} className="text-sm font-extrabold text-ink tracking-tight">
            {title}
          </h2>
          <p id={descriptionId} className="text-xs text-ink-muted leading-relaxed mt-1.5">
            {description}
          </p>
        </div>

        {fields.map((field) => {
          const id = `${fieldId}-${field.name}`;
          const value = draft[field.name];
          if (field.kind === "checkbox") {
            return (
              <label key={field.name} htmlFor={id} className="flex items-center gap-2 text-xs font-semibold text-ink">
                <input
                  id={id}
                  type="checkbox"
                  checked={Boolean(value)}
                  onChange={(event) => set(field.name, event.target.checked)}
                  disabled={saving}
                  className="h-4 w-4 accent-primary"
                />
                {field.label}
              </label>
            );
          }
          return (
            <div key={field.name}>
              <label htmlFor={id} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
                {field.label}
              </label>
              {field.kind === "textarea" ? (
                <textarea
                  id={id}
                  rows={3}
                  value={String(value ?? "")}
                  onChange={(event) => set(field.name, event.target.value)}
                  disabled={saving}
                  className={INPUT_CLASS}
                />
              ) : (
                <input
                  id={id}
                  type="text"
                  inputMode={field.inputMode ?? "text"}
                  value={String(value ?? "")}
                  onChange={(event) => set(field.name, event.target.value)}
                  disabled={saving}
                  className={INPUT_CLASS}
                />
              )}
              {field.hint && <p className="text-[11px] text-ink-muted mt-1">{field.hint}</p>}
            </div>
          );
        })}

        {error && (
          <div role="alert" className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-medium">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
