"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import Image from "next/image";
import Dialog from "@/components/feedback/Dialog";
import { AdminApiError } from "@/lib/admin-api";
import { formatImageUrl } from "@/lib/api";
import { imageFileError, isSessionRequired } from "./editSession";

/** An image field holds the chosen File, or "" while the saved photo stays. */
export type EditValues = Record<string, string | boolean | File>;

export interface EditField {
  name: string;
  label: string;
  kind?: "text" | "textarea" | "checkbox" | "image";
  inputMode?: "text" | "numeric" | "decimal" | "tel" | "email";
  hint?: string;
  /** For an image field: the saved photo, shown until another is chosen. */
  currentUrl?: string | null;
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

  const set = (name: string, value: string | boolean | File) => {
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
          if (field.kind === "image") {
            return (
              <ImageInput
                key={field.name}
                id={id}
                field={field}
                chosen={value instanceof File ? value : null}
                disabled={saving}
                onChange={(file) => set(field.name, file ?? "")}
                onRefused={setError}
              />
            );
          }
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

interface ImageInputProps {
  id: string;
  field: EditField;
  chosen: File | null;
  disabled: boolean;
  onChange: (file: File | null) => void;
  onRefused: (message: string) => void;
}

/** The saved photo, or the one chosen to replace it, with a way back. */
function ImageInput({ id, field, chosen, disabled, onChange, onRefused }: ImageInputProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview]
  );

  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Cleared so choosing the same file again still counts as a change.
    event.target.value = "";
    if (!file) return;
    const refused = imageFileError(file);
    if (refused) {
      onRefused(refused);
      return;
    }
    setPreview(URL.createObjectURL(file));
    onChange(file);
  };

  const keep = () => {
    setPreview(null);
    onChange(null);
  };

  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-1.5">
        {field.label}
      </label>
      <div className="flex items-center gap-3">
        <Image
          src={(chosen && preview) || formatImageUrl(field.currentUrl)}
          alt={chosen ? "The new photo" : "The current photo"}
          width={64}
          height={64}
          className="w-16 h-16 shrink-0 rounded-lg object-cover border border-line bg-surface-alt"
        />
        <div className="min-w-0 flex flex-wrap items-center gap-2">
          <input
            ref={inputRef}
            id={id}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={pick}
            disabled={disabled}
            className="sr-only"
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
            className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt text-ink font-semibold text-[11px] transition-colors cursor-pointer disabled:opacity-50"
          >
            {chosen ? "Choose another" : "Choose a new photo"}
          </button>
          {chosen && (
            <button
              type="button"
              onClick={keep}
              disabled={disabled}
              className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors cursor-pointer disabled:opacity-50"
            >
              Keep the current one
            </button>
          )}
        </div>
      </div>
      {chosen && <p className="text-[11px] text-ink-muted mt-1 break-all">{chosen.name}</p>}
      {field.hint && <p className="text-[11px] text-ink-muted mt-1">{field.hint}</p>}
    </div>
  );
}
