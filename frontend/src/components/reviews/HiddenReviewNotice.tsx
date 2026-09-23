import React from "react";

/**
 * Shown to an author on their own review after staff hid it. Hidden reviews
 * are left out of the public list and the rating, so without this the author
 * would see "Your review" with no hint that nobody else can.
 */
export default function HiddenReviewNotice({ reason }: { reason?: string }) {
  return (
    <div className="mt-2 p-2.5 rounded-lg bg-accent/10 border border-accent/30 text-xs text-ink-body flex items-start gap-2">
      <span aria-hidden="true" className="material-symbols-outlined text-[16px] text-accent shrink-0">
        visibility_off
      </span>
      <p>
        <strong className="text-accent">Hidden by a moderator.</strong> Other shoppers can&apos;t see
        this review and it doesn&apos;t count toward the rating
        {reason ? (
          <>
            {" "}
            (reason: <span className="text-ink">{reason}</span>)
          </>
        ) : null}
        . Editing it won&apos;t make it visible again.
      </p>
    </div>
  );
}
