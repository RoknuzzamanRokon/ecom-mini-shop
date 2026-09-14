"use client";

import React from "react";
import { createPortal } from "react-dom";

export interface AdminConfirmModalProps {
  open: boolean;
  title: string;
  /** Body copy. Pass a node to compose richer summaries of what will change. */
  message: React.ReactNode;

  confirmLabel?: string;
  cancelLabel?: string;

  /**
   * Receives the trimmed reason (empty string when no reason field is shown).
   * May return a promise; the modal shows its own busy state until it settles.
   */
  onConfirm: (reason: string) => void | Promise<void>;
  onCancel: () => void;

  /** Red confirm button + warning iconography for irreversible operations. */
  destructive?: boolean;
  /** Externally driven busy state, OR-ed with the internal one. */
  loading?: boolean;

  /** Shows a reason textarea — several backend status endpoints require one. */
  requireReason?: boolean;
  reasonLabel?: string;
  reasonPlaceholder?: string;
  /** When true, confirm stays disabled until a non-empty reason is entered. */
  reasonRequired?: boolean;

  /** Material Symbols ligature; defaults by destructive flag. */
  icon?: string;
}

/** No-op subscribe: the "is mounted" snapshot never changes after hydration. */
const subscribeToNothing = () => () => {};

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Reusable confirmation dialog for sensitive management actions
 * (approve, reject, suspend, reactivate, refund, deactivate, role assignment…).
 *
 * This component owns confirmation UX only — it performs no business action and
 * calls no API. The caller supplies onConfirm and remains responsible for the
 * request, and the backend remains the final authorization authority.
 *
 * Accessibility: role="dialog" + aria-modal, labelled and described by its own
 * content, focus moved in on open and restored on close, Tab cycles within the
 * dialog, Escape cancels, and background scroll is locked while open.
 */
export default function AdminConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  destructive = false,
  loading = false,
  requireReason = false,
  reasonLabel = "Reason",
  reasonPlaceholder = "Provide a reason for this decision…",
  reasonRequired = false,
  icon,
}: AdminConfirmModalProps) {
  const [reason, setReason] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const previouslyFocused = React.useRef<HTMLElement | null>(null);

  const titleId = React.useId();
  const descriptionId = React.useId();
  const reasonId = React.useId();

  const busy = loading || submitting;
  const trimmedReason = reason.trim();
  const confirmBlocked = busy || (requireReason && reasonRequired && !trimmedReason);

  /**
   * Portals need a DOM target, which does not exist while server-rendering.
   * useSyncExternalStore gives a stable `false` on the server and `true` on the
   * client, so the first client render matches the server output and hydration
   * stays consistent — without a setState-in-effect round trip.
   */
  const mounted = React.useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false
  );

  /**
   * Reset transient state whenever the dialog transitions closed -> open, so a
   * reason typed into a previous confirmation never leaks into the next one.
   * Adjusting state during render (rather than in an effect) is React's
   * recommended pattern here and avoids a wasted render pass.
   */
  const [wasOpen, setWasOpen] = React.useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setReason("");
      setSubmitting(false);
    }
  }

  // Move focus in on open; restore it to the trigger on close.
  React.useEffect(() => {
    if (!open) return;

    previouslyFocused.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const node = dialogRef.current;
    const firstFocusable = node?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (firstFocusable ?? node)?.focus();

    return () => {
      previouslyFocused.current?.focus();
    };
  }, [open]);

  // Lock background scroll while the dialog is open.
  React.useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  const handleCancel = React.useCallback(() => {
    if (busy) return;
    onCancel();
  }, [busy, onCancel]);

  const handleConfirm = async () => {
    if (confirmBlocked) return;
    try {
      setSubmitting(true);
      await onConfirm(trimmedReason);
    } finally {
      setSubmitting(false);
    }
  };

  // Escape to close, Tab cycles focus within the dialog.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      handleCancel();
      return;
    }

    if (event.key !== "Tab") return;

    const focusables = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? []
    );
    if (focusables.length === 0) return;

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!mounted || !open) return null;

  const resolvedIcon = icon ?? (destructive ? "warning" : "help");

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-6"
      onKeyDown={handleKeyDown}
    >
      {/* Backdrop — click to dismiss */}
      <div
        aria-hidden="true"
        onClick={handleCancel}
        className="absolute inset-0 bg-black/50 backdrop-blur-xs"
      />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="relative w-full sm:max-w-md bg-surface border border-line rounded-t-2xl sm:rounded-2xl shadow-lg p-6 focus:outline-none"
      >
        <div className="flex items-start gap-3.5">
          <div
            className={`w-11 h-11 shrink-0 rounded-xl flex items-center justify-center ${
              destructive
                ? "bg-red-500/10 text-red-600"
                : "bg-primary/10 text-primary"
            }`}
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[24px]">
              {resolvedIcon}
            </span>
          </div>

          <div className="flex-1 min-w-0">
            <h2 id={titleId} className="text-sm font-extrabold text-ink tracking-tight">
              {title}
            </h2>
            <div
              id={descriptionId}
              className="text-xs text-ink-muted leading-relaxed mt-1.5"
            >
              {message}
            </div>
          </div>
        </div>

        {requireReason && (
          <div className="mt-4">
            <label
              htmlFor={reasonId}
              className="block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5"
            >
              {reasonLabel}
              {reasonRequired && (
                <span className="text-red-600 ml-0.5" aria-hidden="true">
                  *
                </span>
              )}
            </label>
            <textarea
              id={reasonId}
              rows={3}
              value={reason}
              disabled={busy}
              required={reasonRequired}
              placeholder={reasonPlaceholder}
              onChange={(e) => setReason(e.target.value)}
              className="w-full bg-surface border border-line rounded-lg px-3 py-2 text-xs text-ink placeholder:text-ink-faint resize-none transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50"
            />
            {reasonRequired && !trimmedReason && (
              <p className="text-[10px] text-ink-faint mt-1">
                A reason is required before you can continue.
              </p>
            )}
          </div>
        )}

        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2.5">
          <button
            type="button"
            onClick={handleCancel}
            disabled={busy}
            className="px-4 py-2.5 rounded-lg border border-line text-ink hover:bg-surface-alt font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {cancelLabel}
          </button>

          <button
            type="button"
            onClick={handleConfirm}
            disabled={confirmBlocked}
            className={`inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-xs uppercase tracking-wider transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 ${
              destructive
                ? "bg-red-600 hover:bg-red-700 text-white focus-visible:outline-red-600"
                : "bg-primary hover:bg-primary-hover text-on-primary focus-visible:outline-primary"
            }`}
          >
            {busy && (
              <span
                aria-hidden="true"
                className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
              />
            )}
            {busy ? "Processing…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
