"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AttachmentPicker from "@/components/support/AttachmentPicker";
import { createSupportTicket, getSellerOrders, getUserOrders } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import {
  SUPPORT_LIMITS,
  type SupportOrderOption,
  type SupportPortalConfig,
  formatSupportDateTime,
} from "@/lib/support";
import type { SupportCategory } from "@/lib/types";

type FieldErrors = Partial<Record<"category" | "subject" | "description", string>>;

/** The requester's recent orders for the "Related order" choice, per channel. */
async function loadRecentOrders(
  portal: SupportPortalConfig,
  token: string
): Promise<SupportOrderOption[]> {
  const page = portal.channel === "SELLER" ? await getSellerOrders(token) : await getUserOrders(token, 1);
  return page.results;
}

/** Category a ?order= link preselects: the channel's order category. */
const ORDER_CATEGORY: Record<SupportPortalConfig["channel"], SupportCategory> = {
  CUSTOMER: "ORDER",
  SELLER: "FULFILLMENT",
};

/** The new-ticket form, for the customer profile or the Seller Center. */
export default function SupportNewTicketPage({ portal }: { portal: SupportPortalConfig }) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col items-center justify-center py-20 text-center" role="status">
          <span aria-hidden="true" className="material-symbols-outlined text-[40px] text-ink-muted/50 animate-pulse">
            support_agent
          </span>
          <p className="text-sm text-ink-body mt-2">Loading…</p>
        </div>
      }
    >
      <NewTicketForm portal={portal} />
    </Suspense>
  );
}

function validate(category: SupportCategory | "", subject: string, description: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!category) errors.category = "Choose what your problem is about.";
  if (subject.trim().length < SUPPORT_LIMITS.subjectMin) {
    errors.subject = `Subject must be at least ${SUPPORT_LIMITS.subjectMin} characters.`;
  }
  if (description.trim().length < SUPPORT_LIMITS.descriptionMin) {
    errors.description = `Please describe the problem in at least ${SUPPORT_LIMITS.descriptionMin} characters.`;
  }
  return errors;
}

function NewTicketForm({ portal }: { portal: SupportPortalConfig }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orderFromLink = (searchParams.get("order") ?? "").trim();
  // ?category= (e.g. the wallet's "Request points" link) preselects a category
  // this channel offers; anything else is ignored.
  const categoryFromLink = portal.categories.find(
    (option) => option.value === (searchParams.get("category") ?? "").trim().toUpperCase()
  )?.value;

  const [category, setCategory] = useState<SupportCategory | "">(
    categoryFromLink ?? (orderFromLink ? ORDER_CATEGORY[portal.channel] : "")
  );
  const [orderNumber, setOrderNumber] = useState(orderFromLink);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [orders, setOrders] = useState<SupportOrderOption[]>([]);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // The requester's most recent orders, for the "Related order" choice. If this
  // fails the form still works; the order is simply optional.
  useEffect(() => {
    const token = getAuthToken();
    if (!token) return;
    let cancelled = false;
    loadRecentOrders(portal, token)
      .then((recent) => {
        if (!cancelled) setOrders(recent);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [portal]);

  // A linked order number that isn't among the recent ones still gets an option.
  const orderOptions =
    orderFromLink && !orders.some((o) => o.order_number === orderFromLink)
      ? [{ order_number: orderFromLink, label: `Order ${orderFromLink}` }]
      : [];

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    const errors = validate(category, subject, description);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0 || !category) return;

    const token = getAuthToken();
    if (!token) {
      setFormError("Please log in again.");
      return;
    }
    setSubmitting(true);
    try {
      const ticket = await createSupportTicket(
        {
          category,
          subject: subject.trim(),
          description: description.trim(),
          order_number: orderNumber || undefined,
          attachments: files,
        },
        token,
        portal.channel
      );
      router.push(`${portal.basePath}/${encodeURIComponent(ticket.ticket_number)}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Your ticket couldn't be sent. Please try again.");
      setSubmitting(false);
    }
  };

  const inputClass = (invalid: boolean) =>
    `w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
      invalid ? "border-danger" : "border-line"
    }`;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href={portal.basePath}
          className="inline-flex items-center gap-1 text-xs font-semibold text-ink-muted hover:text-primary transition-colors"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
            arrow_back
          </span>
          All tickets
        </Link>
        <h1 className="text-xl font-bold text-ink mt-2">New support ticket</h1>
        <p className="text-xs text-ink-muted mt-0.5">{portal.copy.newIntro}</p>
      </div>

      <form
        onSubmit={handleSubmit}
        noValidate
        className="bg-surface rounded-2xl border border-line shadow-sm p-4 sm:p-6 flex flex-col gap-6"
      >
        {formError && (
          <div role="alert" className="flex items-start gap-2 p-3 rounded-lg border border-danger/40 bg-danger/10 text-sm text-danger">
            <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0">
              error
            </span>
            <p>{formError}</p>
          </div>
        )}

        <fieldset aria-describedby={fieldErrors.category ? "support-category-error" : undefined}>
          <legend className="text-sm font-bold text-ink mb-2">
            What is it about? <span className="text-danger">*</span>
          </legend>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {portal.categories.map((option) => {
              const selected = category === option.value;
              return (
                <label
                  key={option.value}
                  className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-xs font-semibold cursor-pointer transition-colors has-focus-visible:ring-2 has-focus-visible:ring-focus ${
                    selected
                      ? "bg-primary text-on-primary border-primary shadow-sm"
                      : "bg-surface text-ink border-line hover:bg-surface-alt"
                  }`}
                >
                  <input
                    type="radio"
                    name="category"
                    value={option.value}
                    checked={selected}
                    onChange={() => setCategory(option.value)}
                    className="sr-only"
                  />
                  <span aria-hidden="true" className="material-symbols-outlined text-[18px] shrink-0">
                    {option.icon}
                  </span>
                  <span className="min-w-0">{option.label}</span>
                </label>
              );
            })}
          </div>
          {fieldErrors.category && (
            <p id="support-category-error" className="mt-1.5 text-xs font-semibold text-danger">
              {fieldErrors.category}
            </p>
          )}
        </fieldset>

        <div>
          <label htmlFor="support-order" className="block text-sm font-bold text-ink mb-1.5">
            Related order <span className="font-normal text-ink-muted">(optional)</span>
          </label>
          <select
            id="support-order"
            value={orderNumber}
            onChange={(e) => setOrderNumber(e.target.value)}
            className={inputClass(false)}
          >
            <option value="">Not about an order</option>
            {orderOptions.map((option) => (
              <option key={option.order_number} value={option.order_number}>
                {option.label}
              </option>
            ))}
            {orders.map((order) => (
              <option key={order.order_number} value={order.order_number}>
                {`${order.order_number} · ${formatSupportDateTime(order.created_at).split(",")[0]} · ৳${order.total_amount}`}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-ink-faint">{portal.copy.orderHint}</p>
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-2 mb-1.5">
            <label htmlFor="support-subject" className="text-sm font-bold text-ink">
              Subject <span className="text-danger">*</span>
            </label>
            <span className="text-[11px] text-ink-faint" aria-hidden="true">
              {subject.length}/{SUPPORT_LIMITS.subjectMax}
            </span>
          </div>
          <input
            id="support-subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={SUPPORT_LIMITS.subjectMax}
            placeholder={portal.copy.subjectPlaceholder}
            aria-invalid={Boolean(fieldErrors.subject)}
            aria-describedby={fieldErrors.subject ? "support-subject-error" : undefined}
            className={inputClass(Boolean(fieldErrors.subject))}
          />
          {fieldErrors.subject && (
            <p id="support-subject-error" className="mt-1.5 text-xs font-semibold text-danger">
              {fieldErrors.subject}
            </p>
          )}
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-2 mb-1.5">
            <label htmlFor="support-description" className="text-sm font-bold text-ink">
              Describe the problem <span className="text-danger">*</span>
            </label>
            <span className="text-[11px] text-ink-faint" aria-hidden="true">
              {description.length}/{SUPPORT_LIMITS.messageMax}
            </span>
          </div>
          <textarea
            id="support-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={SUPPORT_LIMITS.messageMax}
            rows={7}
            placeholder={portal.copy.descriptionPlaceholder}
            aria-invalid={Boolean(fieldErrors.description)}
            aria-describedby={`support-description-hint${fieldErrors.description ? " support-description-error" : ""}`}
            className={`${inputClass(Boolean(fieldErrors.description))} resize-y min-h-32`}
          />
          <p id="support-description-hint" className="mt-1 text-[11px] text-ink-faint">
            Please don&apos;t include passwords or full card numbers.
          </p>
          {fieldErrors.description && (
            <p id="support-description-error" className="mt-1 text-xs font-semibold text-danger">
              {fieldErrors.description}
            </p>
          )}
        </div>

        <div>
          <p className="text-sm font-bold text-ink mb-1.5">
            Screenshots or documents <span className="font-normal text-ink-muted">(optional)</span>
          </p>
          <AttachmentPicker files={files} onChange={setFiles} disabled={submitting} />
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-3 pt-2 border-t border-line-subtle">
          <Link
            href={portal.basePath}
            className="text-center px-5 py-2.5 rounded-lg border border-line text-ink text-xs font-bold uppercase tracking-wider hover:bg-surface-alt transition-colors"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-2.5 rounded-lg shadow-sm transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <span aria-hidden="true" className={`material-symbols-outlined text-[18px] ${submitting ? "animate-spin" : ""}`}>
              {submitting ? "progress_activity" : "send"}
            </span>
            {submitting ? "Sending…" : "Send ticket"}
          </button>
        </div>
      </form>
    </div>
  );
}
