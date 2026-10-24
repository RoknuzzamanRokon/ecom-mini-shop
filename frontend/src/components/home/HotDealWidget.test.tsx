import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { HotDeal } from "@/lib/types";

import HotDealWidget, { dealDiscountPercent, timeLeftUntil } from "./HotDealWidget";

vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("@/context/CartContext", () => ({ useCart: () => ({ addToCart: vi.fn() }) }));

function deal(overrides: Partial<HotDeal> = {}): HotDeal {
  return {
    id: 1,
    name: "Desk Lamp",
    slug: "desk-lamp",
    description: "",
    price: "500.00",
    old_price: null,
    stock: 5,
    is_active: true,
    in_stock: true,
    discount_percent: 0,
    created_at: "2026-01-01T00:00:00Z",
    deal_ends_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.useRealTimers();
});

describe("HotDealWidget (BUG-085)", () => {
  it("shows no discount badge, struck price or countdown when there is no real deal", () => {
    render(<HotDealWidget deal={deal()} />);

    expect(screen.getByText("Desk Lamp")).toBeInTheDocument();
    expect(screen.queryByText(/OFF/)).not.toBeInTheDocument();
    expect(screen.queryByText(/49%/)).not.toBeInTheDocument();
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
    expect(screen.queryByText("chevron_left")).not.toBeInTheDocument();
  });

  it("shows the real discount", () => {
    render(<HotDealWidget deal={deal({ price: "400.00", old_price: "500.00", discount_percent: 20 })} />);

    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("৳500.00")).toHaveClass("line-through");
  });

  it("counts down to the API's end time and disappears once it passes", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-24T10:00:00Z"));
    render(<HotDealWidget deal={deal({ deal_ends_at: "2026-10-25T12:30:05Z" })} />);

    const timer = screen.getByRole("timer", { name: "Time left in this deal" });
    expect(timer).toHaveTextContent(/1\s*Days\s*02\s*Hrs\s*30\s*Mins\s*05\s*Secs/);

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(timer).toHaveTextContent(/03\s*Secs/);

    act(() => {
      vi.setSystemTime(new Date("2026-10-25T12:30:06Z"));
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });
});

describe("dealDiscountPercent", () => {
  it.each([
    [{ discount_percent: 18 }, 18],
    [{ discount_percent: undefined, price: "80.00", old_price: "100.00" }, 20],
    [{ discount_percent: undefined, price: "120.00", old_price: "100.00" }, 0],
    [{ discount_percent: undefined, old_price: null }, 0],
  ])("is %j -> %i", (overrides, expected) => {
    expect(dealDiscountPercent(deal(overrides as Partial<HotDeal>))).toBe(expected);
  });
});

describe("timeLeftUntil", () => {
  it("is null once the end has passed", () => {
    expect(timeLeftUntil(1_000, 1_000)).toBeNull();
    expect(timeLeftUntil(1_000, 5_000)).toBeNull();
  });
});
