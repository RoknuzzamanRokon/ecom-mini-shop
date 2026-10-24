import { describe, expect, it } from "vitest";

import { POINT_TRANSACTION_TYPE_OPTIONS } from "./sellerGovernance";

describe("POINT_TRANSACTION_TYPE_OPTIONS", () => {
  it("offers every PointTransaction type, EXPIRY included (BUG-080)", () => {
    expect(POINT_TRANSACTION_TYPE_OPTIONS.map((option) => option.value)).toEqual([
      "BONUS",
      "ADMIN_CREDIT",
      "ADMIN_DEBIT",
      "PRODUCT_CREATION",
      "REFUND",
      "ADJUSTMENT",
      "EXPIRY",
    ]);
    expect(POINT_TRANSACTION_TYPE_OPTIONS).toContainEqual({ value: "EXPIRY", label: "Points Expired" });
  });
});
