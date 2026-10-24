"use client";

import React, { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

export interface DialogProps {
  open: boolean;
  /** Escape or a backdrop click. Not called while `dismissible` is false. */
  onClose: () => void;
  /** False while something is in flight that closing would orphan. */
  dismissible?: boolean;
  /** The id of the visible heading that names the dialog. */
  labelledBy?: string;
  /** The dialog's name when it has no visible heading. */
  label?: string;
  /** The id of the element describing the dialog. */
  describedBy?: string;
  /**
   * Where the panel sits: centred, a bottom sheet on phones that centres
   * from `sm` up, or a full-height drawer on the right.
   */
  placement?: "center" | "sheet" | "right";
  /** Stacking order of the whole overlay. */
  zIndexClass?: string;
  /** Classes for the dialog panel itself. */
  className?: string;
  /** What gets focus on open; by default the first focusable control. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  children: React.ReactNode;
}

const PLACEMENT_CLASSES: Record<NonNullable<DialogProps["placement"]>, string> = {
  center: "items-center justify-center p-4",
  sheet: "items-end sm:items-center justify-center p-0 sm:p-6",
  right: "justify-end",
};

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** No-op subscribe: the "is mounted" snapshot never changes after hydration. */
const subscribeToNothing = () => () => {};

/**
 * The one modal dialog every popup builds on (BUG-094): the cart drawer, the
 * cancel-order dialog and the Console's confirmations.
 *
 * - role="dialog", aria-modal and a name (`labelledBy` or `label`);
 * - focus moves in on open (the first control, or `initialFocusRef`), Tab and
 *   Shift+Tab cycle inside, and focus returns to what had it on close;
 * - Escape and a backdrop click call `onClose`, unless `dismissible` is false;
 * - the page behind does not scroll while it is open.
 *
 * Rendered into document.body through a portal, so no ancestor's overflow or
 * stacking context can clip it.
 */
export default function Dialog({
  open,
  onClose,
  dismissible = true,
  labelledBy,
  label,
  describedBy,
  placement = "center",
  zIndexClass = "z-50",
  className = "",
  initialFocusRef,
  children,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // Portals need document.body, which the server does not have.
  const mounted = useSyncExternalStore(subscribeToNothing, () => true, () => false);

  // Focus in on open; back to the opener on close.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    const target =
      initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? panel;
    target?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
    // initialFocusRef is read once, when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // The page behind stays put.
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  const requestClose = useCallback(() => {
    if (dismissible) onClose();
  }, [dismissible, onClose]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      requestClose();
      return;
    }
    if (event.key !== "Tab") return;

    const focusables = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? []);
    if (focusables.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;
    const outside = !panelRef.current?.contains(active);
    if (event.shiftKey && (active === first || outside)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || outside)) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!mounted || !open) return null;

  return createPortal(
    <div className={`fixed inset-0 flex ${PLACEMENT_CLASSES[placement]} ${zIndexClass}`} onKeyDown={onKeyDown}>
      <div aria-hidden="true" onClick={requestClose} className="absolute inset-0 bg-black/50 backdrop-blur-xs" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={`relative focus:outline-none ${className}`}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}
