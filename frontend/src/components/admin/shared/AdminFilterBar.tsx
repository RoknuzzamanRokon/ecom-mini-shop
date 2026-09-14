"use client";

import React from "react";

/**
 * Composable filter container for management list pages.
 *
 * Deliberately domain-agnostic: it lays out and resets whatever fields a page
 * composes into it. The field primitives below cover the patterns the admin
 * modules need (search, select/status, date), and a page is free to drop in any
 * other control as a child.
 */
export interface AdminFilterBarProps {
  children: React.ReactNode;
  /** Shows the reset control when true. */
  isDirty?: boolean;
  onReset?: () => void;
  resetLabel?: string;
  /** Rendered at the far right, e.g. a "New category" button or result count. */
  trailing?: React.ReactNode;
  /** Accessible group label, announced to screen readers. */
  label?: string;
  className?: string;
}

export default function AdminFilterBar({
  children,
  isDirty = false,
  onReset,
  resetLabel = "Clear",
  trailing,
  label = "Filters",
  className = "",
}: AdminFilterBarProps) {
  return (
    <section
      aria-label={label}
      className={`bg-surface rounded-2xl border border-line shadow-xs p-3 sm:p-4 ${className}`}
    >
      <div className="flex flex-col lg:flex-row lg:items-end gap-3">
        <div className="flex-1 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-end gap-3">
          {children}
        </div>

        {(onReset || trailing) && (
          <div className="flex items-center gap-2 shrink-0">
            {onReset && isDirty && (
              <button
                type="button"
                onClick={onReset}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line text-ink-muted hover:text-ink hover:bg-surface-alt text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                  filter_alt_off
                </span>
                {resetLabel}
              </button>
            )}
            {trailing}
          </div>
        )}
      </div>
    </section>
  );
}

// =============================================================================
// FIELD PRIMITIVES
// =============================================================================

const FIELD_LABEL_CLASS =
  "block text-[10px] font-extrabold uppercase tracking-wider text-ink-muted mb-1.5";

const FIELD_CONTROL_CLASS =
  "w-full bg-surface border border-line rounded-lg text-xs text-ink placeholder:text-ink-faint transition-colors focus:outline-none focus:border-primary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary disabled:opacity-50 disabled:cursor-not-allowed";

export interface AdminSearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  /** Fires on Enter, for pages that search on submit rather than on change. */
  onSubmit?: (value: string) => void;
  disabled?: boolean;
  className?: string;
}

/** Text search input with a clear button. Debouncing is the caller's choice. */
export function AdminSearchField({
  value,
  onChange,
  label = "Search",
  placeholder = "Search…",
  onSubmit,
  disabled = false,
  className = "sm:w-64",
}: AdminSearchFieldProps) {
  const id = React.useId();

  return (
    <div className={`w-full ${className}`}>
      <label htmlFor={id} className={FIELD_LABEL_CLASS}>
        {label}
      </label>
      <div className="relative">
        <span
          aria-hidden="true"
          className="material-symbols-outlined text-[18px] text-ink-faint absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
        >
          search
        </span>
        <input
          id={id}
          type="search"
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && onSubmit) {
              e.preventDefault();
              onSubmit(value);
            }
          }}
          className={`${FIELD_CONTROL_CLASS} pl-9 pr-8 py-2`}
        />
        {value && !disabled && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink p-0.5 rounded cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              close
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

export interface AdminSelectOption {
  value: string;
  label: string;
}

export interface AdminSelectFieldProps {
  label: string;
  value: string;
  options: AdminSelectOption[];
  onChange: (value: string) => void;
  /** Label for the "no filter" option; pass null to omit it. */
  placeholder?: string | null;
  disabled?: boolean;
  className?: string;
}

/**
 * Dropdown filter. Used for status filters by passing the domain's real status
 * values as options — this component never hardcodes any domain status itself.
 */
export function AdminSelectField({
  label,
  value,
  options,
  onChange,
  placeholder = "All",
  disabled = false,
  className = "sm:w-44",
}: AdminSelectFieldProps) {
  const id = React.useId();

  return (
    <div className={`w-full ${className}`}>
      <label htmlFor={id} className={FIELD_LABEL_CLASS}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={`${FIELD_CONTROL_CLASS} px-2.5 py-2 cursor-pointer`}
      >
        {placeholder !== null && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export interface AdminDateFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** ISO yyyy-mm-dd bounds, e.g. to keep "to" at or after "from". */
  min?: string;
  max?: string;
  disabled?: boolean;
  className?: string;
}

/** Date filter emitting an ISO `yyyy-mm-dd` string, matching the admin APIs. */
export function AdminDateField({
  label,
  value,
  onChange,
  min,
  max,
  disabled = false,
  className = "sm:w-40",
}: AdminDateFieldProps) {
  const id = React.useId();

  return (
    <div className={`w-full ${className}`}>
      <label htmlFor={id} className={FIELD_LABEL_CLASS}>
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={`${FIELD_CONTROL_CLASS} px-2.5 py-2 cursor-pointer`}
      />
    </div>
  );
}
