import { describe, expect, it } from "vitest";

import { formatBangladeshiMobile, normalizeBangladeshiMobile } from "./phone";

describe("normalizeBangladeshiMobile", () => {
  it.each([
    "01712345678",
    "8801712345678",
    "+8801712345678",
    "+880 1712 345678",
    "01712-345678",
    " (017) 1234.5678 ",
    "০১৭১২৩৪৫৬৭৮",
  ])("reads %j as +8801712345678", (spelling) => {
    expect(normalizeBangladeshiMobile(spelling)).toBe("+8801712345678");
  });

  it.each([
    "",
    "johndoe",
    "01212345678",
    "0171234567",
    "017123456789",
    "+4401712345678",
    "+88+01712345678",
  ])("refuses %j", (value) => {
    expect(normalizeBangladeshiMobile(value)).toBeNull();
  });
});

describe("formatBangladeshiMobile", () => {
  it("drops the country code", () => {
    expect(formatBangladeshiMobile("+8801712345678")).toBe("01712345678");
  });

  it("leaves anything else alone", () => {
    expect(formatBangladeshiMobile("01712345678")).toBe("01712345678");
  });
});
