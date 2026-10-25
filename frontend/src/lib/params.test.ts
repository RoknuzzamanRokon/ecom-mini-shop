import { describe, expect, it } from "vitest";

import { pageNumber } from "./params";

describe("pageNumber (BUG-118)", () => {
  it.each([
    ["3", 3],
    ["1", 1],
    [null, 1],
    ["", 1],
    ["-1", 1],
    ["0", 1],
    ["1.5", 1],
    ["abc", 1],
  ])("%j -> %i", (raw, expected) => {
    expect(pageNumber(raw)).toBe(expected);
  });
});
