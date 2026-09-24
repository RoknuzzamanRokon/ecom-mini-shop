"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  SUPPORT_FILE_ACCEPT,
  SUPPORT_FILE_HINT,
  SUPPORT_LIMITS,
  formatFileSize,
  isImageType,
  validateSupportFiles,
} from "@/lib/support";

/**
 * A local image preview. The object URL is created and revoked inside the
 * effect and written straight to the <img>, so React's development
 * double-mount can't leave the preview pointing at a revoked URL.
 */
function LocalImagePreview({ file }: { file: File }) {
  const imgRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    if (imgRef.current) imgRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  // A blob: URL set from the effect; next/image can't load it.
  // eslint-disable-next-line @next/next/no-img-element
  return <img ref={imgRef} alt="" className="w-full h-full object-cover" />;
}

interface AttachmentPickerProps {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
  /** Label for the button; defaults to "Attach files". */
  buttonLabel?: string;
}

/**
 * Controlled file picker for ticket messages: JPG / PNG / WebP / PDF, up to
 * 5 files of 5 MB each. Refused files are left out with a message; the
 * backend checks every file's real content again.
 */
export default function AttachmentPicker({
  files,
  onChange,
  disabled = false,
  buttonLabel = "Attach files",
}: AttachmentPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const full = files.length >= SUPPORT_LIMITS.maxFiles;

  const handleSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incoming = Array.from(event.target.files ?? []);
    // Reset so choosing the same file again still fires onChange.
    event.target.value = "";
    if (incoming.length === 0) return;
    const result = validateSupportFiles(files, incoming);
    setError(result.error);
    if (result.files.length !== files.length) onChange(result.files);
  };

  const remove = (index: number) => {
    setError(null);
    onChange(files.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={SUPPORT_FILE_ACCEPT}
          onChange={handleSelect}
          disabled={disabled || full}
          className="hidden"
          tabIndex={-1}
          aria-hidden="true"
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || full}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-line bg-surface hover:bg-surface-alt text-ink text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
            attach_file
          </span>
          {buttonLabel}
          {files.length > 0 && (
            <span className="text-ink-muted font-normal">
              ({files.length}/{SUPPORT_LIMITS.maxFiles})
            </span>
          )}
        </button>
        <span className="text-[11px] text-ink-faint">{SUPPORT_FILE_HINT}</span>
      </div>

      <p role="status" aria-live="polite" className={error ? "text-xs font-semibold text-danger" : "sr-only"}>
        {error ?? ""}
      </p>

      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Files to send">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
              className="flex items-center gap-2 pl-1 pr-1.5 py-1 rounded-lg border border-line bg-surface-alt max-w-full"
            >
              <span className="w-9 h-9 rounded-md overflow-hidden bg-surface-sunken border border-line-subtle flex items-center justify-center shrink-0">
                {isImageType(file.type) ? (
                  <LocalImagePreview file={file} />
                ) : (
                  <span aria-hidden="true" className="material-symbols-outlined text-[20px] text-danger">
                    picture_as_pdf
                  </span>
                )}
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-ink truncate max-w-[10rem] sm:max-w-[14rem]">
                  {file.name}
                </span>
                <span className="block text-[10px] text-ink-muted">{formatFileSize(file.size)}</span>
              </span>
              <button
                type="button"
                onClick={() => remove(index)}
                disabled={disabled}
                aria-label={`Remove ${file.name}`}
                className="w-7 h-7 rounded-md flex items-center justify-center text-ink-muted hover:text-danger hover:bg-surface transition-colors cursor-pointer disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                  close
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
