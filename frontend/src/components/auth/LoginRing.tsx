"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

// The beaded sign-in ring shared by the storefront login (app/login) and the
// management console login (app/admin/login). Styles: "Login ring" in
// globals.css. Each page keeps its own auth flow and renders its form inside.

// 26 diamond beads spaced evenly around the outer ring (percent of the ring box).
// Rounded so the server and client render identical style strings.
const BEADS = Array.from({ length: 26 }, (_, i) => {
  const angle = (i / 26) * 2 * Math.PI;
  return {
    left: `${(50 + 48.5 * Math.sin(angle)).toFixed(2)}%`,
    top: `${(50 - 48.5 * Math.cos(angle)).toFixed(2)}%`,
  };
});

// How long the rings take to sink in (0.9s + the inner ring's 0.15s delay).
export const SUCCESS_ANIMATION_MS = 1050;

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Refs for the ring's form and beads, plus the wrong-credentials effect:
 * the beads flash and the form shakes.
 */
export function useLoginRingEffects() {
  const formRef = useRef<HTMLFormElement>(null);
  const beadsRef = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    []
  );

  // Removing the class and forcing a reflow restarts the animations when
  // errors come in quick succession.
  const playErrorEffect = useCallback(() => {
    const beads = beadsRef.current;
    const form = formRef.current;
    if (!beads || !form) return;
    beads.classList.remove("is-blinking");
    form.classList.remove("is-shaking");
    void beads.offsetWidth;
    beads.classList.add("is-blinking");
    form.classList.add("is-shaking");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      beads.classList.remove("is-blinking");
      form.classList.remove("is-shaking");
    }, 1100);
  }, []);

  return { formRef, beadsRef, playErrorEffect };
}

interface PasswordFieldProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  name?: string;
}

/**
 * The ring's password field, with an eye button that shows or hides what was
 * typed. While disabled (a sign-in in flight) it always renders as a password
 * input, so the form is submitted as one and password managers still offer to
 * save it.
 */
export function LoginRingPasswordField({ value, onChange, disabled, name }: PasswordFieldProps) {
  const [shown, setShown] = useState(false);
  const visible = shown && !disabled;

  return (
    <div className="login-ring__field">
      <label htmlFor="password" className="login-ring__label">
        Password
      </label>
      <div className="login-ring__password">
        <input
          id="password"
          name={name}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter your password"
          autoComplete="current-password"
          disabled={disabled}
          className="login-ring__input"
        />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          disabled={disabled}
          aria-controls="password"
          aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
          title={visible ? "Hide password" : "Show password"}
          className="login-ring__reveal"
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            {visible ? "visibility_off" : "visibility"}
          </span>
        </button>
      </div>
    </div>
  );
}

interface LoginRingProps {
  /** Sinks both rings into the centre and fades `welcome` in. */
  success: boolean;
  beadsRef: React.RefObject<HTMLDivElement | null>;
  /** Shown once the rings have sunk in, while the redirect happens. */
  welcome: React.ReactNode;
  /** The form, rendered inside the inner ring. */
  children: React.ReactNode;
}

export default function LoginRing({ success, beadsRef, welcome, children }: LoginRingProps) {
  return (
    <div className={`login-ring${success ? " is-success" : ""}`}>
      {/* Outer ring (decorative, rotating) */}
      <div className="login-ring__outer" aria-hidden="true">
        <div className="login-ring__wire" />
        <div className="login-ring__track" />
        <div ref={beadsRef} className="login-ring__beads">
          {BEADS.map((pos, i) => (
            <span key={i} className="login-ring__bead" style={pos} />
          ))}
        </div>
      </div>

      {/* Inner ring holding the form */}
      <div className="login-ring__inner">{children}</div>

      <div
        className={`login-ring__welcome${success ? " is-visible" : ""}`}
        style={success ? { transitionDelay: "0.95s" } : undefined}
        aria-live="polite"
      >
        {success && welcome}
      </div>
    </div>
  );
}
