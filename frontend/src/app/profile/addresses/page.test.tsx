import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteCustomerAddress, getCustomerAddresses } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { Address } from "@/lib/types";

import AddressesPage from "./page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getCustomerAddresses: vi.fn(),
  deleteCustomerAddress: vi.fn(),
}));

const HOME: Address = {
  id: 8,
  label: "Home",
  recipient_name: "Nadia Islam",
  phone: "01711111111",
  address_line_1: "House 4, Road 2",
  city: "Dhaka",
  postal_code: "1207",
  country: "Bangladesh",
  is_default: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(getCustomerAddresses).mockReset().mockResolvedValue([HOME]);
  vi.mocked(deleteCustomerAddress).mockReset();
});

describe("Addresses: delete (BUG-091)", () => {
  it("asks first, then deletes", async () => {
    vi.mocked(deleteCustomerAddress).mockResolvedValue();
    render(<AddressesPage />);
    await screen.findByText("Nadia Islam");

    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    expect(deleteCustomerAddress).not.toHaveBeenCalled();
    const question = screen.getByRole("group", { name: "Delete this address?" });

    await act(async () => {
      fireEvent.click(within(question).getByRole("button", { name: "Delete" }));
    });
    expect(deleteCustomerAddress).toHaveBeenCalledWith(8, "access");
    expect(screen.queryByText("Nadia Islam")).not.toBeInTheDocument();
  });

  it("keeps the address and says why when the delete fails", async () => {
    vi.mocked(deleteCustomerAddress).mockRejectedValue(new Error("This address is on an open order."));
    render(<AddressesPage />);
    await screen.findByText("Nadia Islam");

    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    await act(async () => {
      fireEvent.click(
        within(screen.getByRole("group", { name: "Delete this address?" })).getByRole("button", { name: "Delete" })
      );
    });

    expect(screen.getByRole("alert")).toHaveTextContent("This address is on an open order.");
    expect(screen.getByText("Nadia Islam")).toBeInTheDocument();
  });
});
