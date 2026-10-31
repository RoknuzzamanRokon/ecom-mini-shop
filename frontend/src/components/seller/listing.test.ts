import { describe, expect, it } from "vitest";

import { daysLeft, expiriesByDate, listingPeriodLine } from "./listing";

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
