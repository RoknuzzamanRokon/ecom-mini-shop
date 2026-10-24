"use client";

import React, { useEffect, useRef } from "react";

export interface InlineConfirmProps {
  /** The question, e.g. "Delete your review?". Also names the group for screen readers. */
  question: string;
  confirmLabel: string;
  /** Shown on the confirm button while the action runs. */
  busyLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * An irreversible action asked about in place, where its button was: the
 * question, a confirm button and a way back (BUG-091). Focus moves to the way
 * back, so Enter on a repeated keypress never confirms by accident.
 */
export default function InlineConfirm({
  question,
  confirmLabel,
  busyLabel,
  cancelLabel = "Cancel",
  busy = false,
  onConfirm,
  onCancel,
}: InlineConfirmProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  return (
    <div role="group" aria-label={question} className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-semibold text-ink">{question}</span>
      <button
        type="button"
        onClick={onConfirm}
        disabled={busy}
        className="bg-accent hover:opacity-90 disabled:opacity-50 text-on-accent font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg transition-opacity cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {busy && busyLabel ? busyLabel : confirmLabel}
      </button>
      <button
        ref={cancelRef}
        type="button"
        onClick={onCancel}
        disabled={busy}
        className="font-bold uppercase tracking-wider text-ink-muted hover:text-ink px-2 py-1.5 rounded-lg disabled:opacity-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {cancelLabel}
      </button>
    </div>
  );
}
