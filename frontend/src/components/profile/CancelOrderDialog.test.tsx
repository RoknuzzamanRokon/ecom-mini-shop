import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cancelCustomerOrder } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { Order } from "@/lib/types";
import { axeViolations } from "@/test/axe";

import OrderCard from "./OrderCard";

vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  cancelCustomerOrder: vi.fn(),
}));

const ORDER = {
  id: 5,
  order_number: "MS-0005",
  status: "PENDING",
  can_cancel: true,
  total_amount: "500.00",
  items: [],
  created_at: "2026-10-01T00:00:00Z",
} as unknown as Order;

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(cancelCustomerOrder).mockReset();
});

describe("Cancel order dialog (BUG-094)", () => {
  it("opens as a named dialog and gives focus back to Cancel Order on Escape", async () => {
    const user = userEvent.setup();
    render(<OrderCard order={ORDER} />);
    const trigger = screen.getByRole("button", { name: "Cancel Order" });

    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Cancel Order" });
    expect(dialog).toHaveAccessibleDescription(/Are you sure you want to cancel this order/);
    expect(screen.getByLabelText("Reason for cancellation (optional)")).toHaveFocus();
    expect(await axeViolations()).toEqual([]);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(cancelCustomerOrder).not.toHaveBeenCalled();
  });

  it("sends the reason, reports the cancelled order and shows a failure as an alert", async () => {
    const user = userEvent.setup();
    const onOrderUpdated = vi.fn();
    vi.mocked(cancelCustomerOrder)
      .mockRejectedValueOnce(new Error("This order has already shipped."))
      .mockResolvedValueOnce({ ...ORDER, status: "CANCELLED" } as Order);
    render(<OrderCard order={ORDER} onOrderUpdated={onOrderUpdated} />);

    await user.click(screen.getByRole("button", { name: "Cancel Order" }));
    await user.type(screen.getByLabelText("Reason for cancellation (optional)"), "Ordered twice");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Confirm Cancellation" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("This order has already shipped.");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Confirm Cancellation" }));
    });
    expect(cancelCustomerOrder).toHaveBeenLastCalledWith("MS-0005", "access", "Ordered twice");
    expect(onOrderUpdated).toHaveBeenCalledWith(expect.objectContaining({ status: "CANCELLED" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
