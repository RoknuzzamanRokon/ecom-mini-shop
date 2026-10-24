import { afterEach, describe, expect, it } from "vitest";

import { formatDate } from "./admin-format";

describe("formatDate", () => {
  const originalTimeZone = process.env.TZ;
  afterEach(() => {
    process.env.TZ = originalTimeZone;
  });

  it.each(["America/New_York", "America/Los_Angeles", "UTC", "Asia/Dhaka", "Pacific/Auckland"])(
    "shows a date-only value as the same day in %s (BUG-098)",
    (timeZone) => {
      process.env.TZ = timeZone;
      expect(formatDate("1990-05-14")).toBe("14 May 1990");
    }
  );

  it("shows a timestamp in the viewer's time zone", () => {
    process.env.TZ = "America/New_York";
    expect(formatDate("2026-05-14T02:00:00Z")).toBe("13 May 2026");
    process.env.TZ = "Asia/Dhaka";
    expect(formatDate("2026-05-13T20:00:00Z")).toBe("14 May 2026");
  });

  it.each([[null], [undefined], [""], ["not a date"]])("shows a dash for %j", (value) => {
    expect(formatDate(value)).toBe("—");
  });
});
