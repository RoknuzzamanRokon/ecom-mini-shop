"use client";

import React, { useEffect, useRef, useState } from "react";
import type { SupportAttachment } from "@/lib/types";
import { formatFileSize, isImageType } from "@/lib/support";

/**
 * Loads a private attachment. `url` is an /api/support/ path that needs the
 * bearer token, so the page passes a function that fetches it (for example
 * fetchSupportAttachment or fetchAdminSupportAttachment with the token).
 * Keep it stable (useCallback): it is an effect dependency.
 */
export type AttachmentLoader = (url: string) => Promise<Blob>;

interface SecureAttachmentProps {
  attachment: SupportAttachment;
  load: AttachmentLoader;
}

/** How long an opened file's object URL is kept for the new tab. */
const OPENED_URL_LIFETIME_MS = 60_000;

/**
 * Images are fetched straight away and shown as a thumbnail that opens full
 * size in a new tab. Other files (PDFs) are fetched only when clicked. Object
 * URLs are written to the DOM from effects, never kept in state, so React's
 * development double-mount can't leave a revoked URL on screen.
 */
function ImageAttachment({ attachment, load }: SecureAttachmentProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const linkRef = useRef<HTMLAnchorElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    load(attachment.url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        if (imgRef.current) imgRef.current.src = objectUrl;
        if (linkRef.current) linkRef.current.href = objectUrl;
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attachment.url, load]);

  return (
    <a
      ref={linkRef}
      target="_blank"
      rel="noopener noreferrer"
      title={`${attachment.name} (${formatFileSize(attachment.size)})`}
      aria-label={`Open ${attachment.name}`}
      aria-disabled={status !== "ready"}
      onClick={(event) => {
        if (status !== "ready") event.preventDefault();
      }}
      className="group relative block w-24 h-24 rounded-lg overflow-hidden border border-line bg-surface-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      {/* A blob: URL set from the effect; next/image can't load it. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imgRef}
        alt={attachment.name}
        className={`w-full h-full object-cover transition-transform group-hover:scale-105 ${
          status === "ready" ? "" : "invisible"
        }`}
      />
      {status === "loading" && (
        <span aria-hidden="true" className="absolute inset-0 animate-pulse bg-surface-alt" />
      )}
      {status === "error" && (
        <span className="absolute inset-0 flex flex-col items-center justify-center gap-0.5 p-1 text-center text-[10px] text-ink-muted">
          <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
            broken_image
          </span>
          Couldn&apos;t load
        </span>
      )}
    </a>
  );
}

function FileAttachment({ attachment, load }: SecureAttachmentProps) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const open = async () => {
    setBusy(true);
    setFailed(false);
    try {
      const url = URL.createObjectURL(await load(attachment.url));
      const opened = window.open(url, "_blank");
      if (opened) {
        opened.opener = null;
      } else {
        // Pop-up blocked: download it instead.
        const link = document.createElement("a");
        link.href = url;
        link.download = attachment.name;
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), OPENED_URL_LIFETIME_MS);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={open}
      disabled={busy}
      aria-label={`Open ${attachment.name}`}
      className="flex items-center gap-2 max-w-full pl-2 pr-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-left transition-colors cursor-pointer disabled:cursor-wait focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      <span aria-hidden="true" className={`material-symbols-outlined text-[22px] shrink-0 ${busy ? "animate-spin text-ink-muted" : "text-danger"}`}>
        {busy ? "progress_activity" : "picture_as_pdf"}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold text-ink truncate max-w-[12rem]">{attachment.name}</span>
        <span className={`block text-[10px] ${failed ? "text-danger font-semibold" : "text-ink-muted"}`}>
          {failed ? "Couldn't open — try again" : formatFileSize(attachment.size)}
        </span>
      </span>
    </button>
  );
}

/** One private ticket attachment: an image thumbnail or a file button. */
export default function SecureAttachment({ attachment, load }: SecureAttachmentProps) {
  return isImageType(attachment.content_type) ? (
    <ImageAttachment attachment={attachment} load={load} />
  ) : (
    <FileAttachment attachment={attachment} load={load} />
  );
}
