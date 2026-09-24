import React from "react";
import type { SupportAttachment, SupportAuthorType } from "@/lib/types";
import { formatSupportDateTime } from "@/lib/support";
import SecureAttachment, { type AttachmentLoader } from "./SecureAttachment";

/** What the thread needs from a message; both the customer and staff shapes fit. */
export interface ThreadMessage {
  id: number;
  author_type: SupportAuthorType;
  author_name: string;
  body: string;
  created_at: string;
  attachments: SupportAttachment[];
  /** Staff shape only. */
  is_internal?: boolean;
}

interface TicketThreadProps {
  messages: ThreadMessage[];
  /** Whose screen this is: their own messages sit on the right. */
  viewer: "customer" | "staff";
  loadAttachment: AttachmentLoader;
}

function Attachments({ items, load }: { items: SupportAttachment[]; load: AttachmentLoader }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-2" aria-label="Attachments">
      {items.map((attachment) => (
        <li key={attachment.id}>
          <SecureAttachment attachment={attachment} load={load} />
        </li>
      ))}
    </ul>
  );
}

function SystemLine({ message }: { message: ThreadMessage }) {
  return (
    <li className="flex justify-center">
      <p
        className={`inline-flex items-center gap-1.5 max-w-full px-3 py-1 rounded-full text-[11px] text-center ${
          message.is_internal
            ? "bg-accent/10 text-ink-body border border-dashed border-accent/40"
            : "bg-surface-sunken text-ink-muted"
        }`}
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[14px] shrink-0">
          {message.is_internal ? "lock" : "info"}
        </span>
        {message.is_internal && <span className="sr-only">Staff only:</span>}
        <span className="break-words">{message.body}</span>
        <span aria-hidden="true">·</span>
        <time dateTime={message.created_at} className="whitespace-nowrap">
          {formatSupportDateTime(message.created_at)}
        </time>
      </p>
    </li>
  );
}

/**
 * A ticket conversation. Message text is plain text (whitespace kept), never
 * HTML. On the staff screen internal notes are marked and tinted; customers
 * never receive them.
 */
export default function TicketThread({ messages, viewer, loadAttachment }: TicketThreadProps) {
  const ownType: SupportAuthorType = viewer === "customer" ? "CUSTOMER" : "STAFF";

  return (
    <ol className="space-y-4" aria-label="Conversation">
      {messages.map((message) => {
        if (message.author_type === "SYSTEM") {
          return <SystemLine key={message.id} message={message} />;
        }
        const own = message.author_type === ownType;
        const internal = Boolean(message.is_internal);
        const bubble = internal
          ? "bg-accent/10 border-accent/40 border-dashed"
          : own
            ? "bg-primary/10 border-primary/20"
            : "bg-surface border-line";

        return (
          <li key={message.id} className={`flex ${own ? "justify-end" : "justify-start"}`}>
            <article className={`w-full max-w-[92%] sm:max-w-[80%] rounded-2xl border px-4 py-3 ${bubble}`}>
              <header className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mb-1">
                <span className="text-xs font-bold text-ink">{message.author_name}</span>
                {internal && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent">
                    <span aria-hidden="true" className="material-symbols-outlined text-[13px]">
                      lock
                    </span>
                    Internal note · staff only
                  </span>
                )}
                <time dateTime={message.created_at} className="text-[11px] text-ink-muted">
                  {formatSupportDateTime(message.created_at)}
                </time>
              </header>
              {message.body && (
                <p className="text-sm text-ink-body whitespace-pre-wrap break-words">{message.body}</p>
              )}
              <Attachments items={message.attachments} load={loadAttachment} />
            </article>
          </li>
        );
      })}
    </ol>
  );
}
