import { describe, expect, it } from "vitest";

import type { AdminOrderDetail, AdminOrderListItem } from "@/lib/admin-api";

import { mergeOrderIntoListRow } from "./orderGovernance";

const CUSTOMER = { id: 3, username: "karim", email: "karim@example.com", name: "Karim", phone: "01700000000" };

const ROW: AdminOrderListItem = {
  id: 9,
  order_number: "MS-0009",
  status: "SHIPPED",
  customer: CUSTOMER,
  subtotal: "1000.00",
  discount_total: "0.00",
  shipping_fee: "60.00",
  total_amount: "1060.00",
  total_items_count: 2,
  payment_status: "PENDING",
  payment_method: "CASH_ON_DELIVERY",
  shipping_city: "Dhaka",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
};

describe("mergeOrderIntoListRow (BUG-100)", () => {
  it("takes the status, payment and updated_at from the action's response", () => {
    const delivered = {
      ...ROW,
      status: "DELIVERED",
      allowed_transitions: [],
      shipping_address: { city: "Dhaka North" },
      items: [],
      payment: { status: "PAID", payment_method: "CASH_ON_DELIVERY" },
      refunds: [],
      updated_at: "2026-10-03T09:30:00Z",
    } as unknown as AdminOrderDetail;

    expect(mergeOrderIntoListRow(ROW, delivered)).toEqual({
      ...ROW,
      status: "DELIVERED",
      payment_status: "PAID",
      updated_at: "2026-10-03T09:30:00Z",
    });
  });

  it("clears the payment columns when the order has no payment", () => {
    const cancelled = {
      ...ROW,
      status: "CANCELLED",
      payment: null,
      updated_at: "2026-10-03T09:30:00Z",
    } as unknown as AdminOrderDetail;

    expect(mergeOrderIntoListRow(ROW, cancelled)).toMatchObject({
      status: "CANCELLED",
      payment_status: null,
      payment_method: null,
    });
  });
});
