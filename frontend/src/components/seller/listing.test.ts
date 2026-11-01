import { describe, expect, it } from "vitest";

import {
  addMonths,
  canDelete,
  canRenew,
  daysLeft,
  expiriesByDate,
  listingPeriodLine,
  renewedUntil,
} from "./listing";

describe("listing period helpers", () => {
  const now = Date.parse("2026-11-01T06:00:00Z");

  it("counts whole days left, rounding up, and 0 once passed", () => {
    expect(daysLeft("2026-11-06T05:00:00Z", now)).toBe(5);
    expect(daysLeft("2026-11-01T07:00:00Z", now)).toBe(1);
    expect(daysLeft("2026-10-31T06:00:00Z", now)).toBe(0);
  });

  it("says when a live product ends, when an expired one ended, or that there is no end", () => {
    expect(listingPeriodLine({ status: "PUBLISHED", live_until: "2027-03-01T06:00:00Z" })).toBe(
      "Live until 01 Mar 2027"
    );
    expect(listingPeriodLine({ status: "EXPIRED", live_until: "2026-10-20T06:00:00Z" })).toBe(
      "Expired 20 Oct 2026"
    );
    expect(listingPeriodLine({ status: "PUBLISHED", live_until: null })).toBe("No end date");
    expect(listingPeriodLine({ status: "SUBMITTED", live_until: null })).toBeNull();
  });

  it("renews live and expired products, and deletes only expired ones", () => {
    expect(canRenew({ status: "PUBLISHED", listing_locked: true })).toBe(true);
    expect(canRenew({ status: "EXPIRED", listing_locked: false })).toBe(true);
    expect(canRenew({ status: "PUBLISHED", listing_locked: false })).toBe(false);
    expect(canRenew({ status: "DRAFT", listing_locked: false })).toBe(false);
    expect(canDelete({ status: "EXPIRED" })).toBe(true);
    expect(canDelete({ status: "PUBLISHED" })).toBe(false);
  });

  it("adds calendar months, clamping the day like the backend", () => {
    expect(addMonths(new Date("2027-01-31T06:00:00Z"), 1).toISOString()).toBe("2027-02-28T06:00:00.000Z");
    expect(addMonths(new Date("2026-11-15T06:00:00Z"), 2).toISOString()).toBe("2027-01-15T06:00:00.000Z");
  });

  it("renews early from the end date, and an expired product from now", () => {
    const live = { status: "PUBLISHED", listing_locked: true, live_until: "2026-11-05T06:00:00Z" };
    expect(renewedUntil(live, 2, now)).toBe("2027-01-05T06:00:00.000Z");
    const expired = { status: "EXPIRED", listing_locked: false, live_until: "2026-10-20T06:00:00Z" };
    expect(renewedUntil(expired, 2, now)).toBe("2027-01-01T06:00:00.000Z");
  });

  it("merges point batches that share an expiry date", () => {
    expect(
      expiriesByDate([
        { points: 90, expires_at: "2026-12-06T06:00:00Z" },
        { points: 100, expires_at: "2026-12-06T06:00:00Z" },
        { points: 5, expires_at: "2027-01-01T06:00:00Z" },
      ])
    ).toEqual([
      { points: 190, expires_at: "2026-12-06T06:00:00Z" },
      { points: 5, expires_at: "2027-01-01T06:00:00Z" },
    ]);
  });
});
