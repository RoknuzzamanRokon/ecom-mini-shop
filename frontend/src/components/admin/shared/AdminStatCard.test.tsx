import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AdminStatCard from "./AdminStatCard";

describe("AdminStatCard", () => {
  it.each([
    ["a missing count", undefined, false],
    ["a missing amount", undefined, true],
    ["a null amount", null, true],
  ])("shows a dash, not a zero, for %s (BUG-083)", (_label, value, currency) => {
    render(<AdminStatCard title="Figure" value={value} currency={currency} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/0/)).not.toBeInTheDocument();
  });

  it("shows a real zero as zero, and money in ৳", () => {
    render(
      <>
        <AdminStatCard title="Orders" value={0} />
        <AdminStatCard title="Revenue" value={1500.5} currency />
      </>
    );
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/৳\s?1,500\.50/)).toBeInTheDocument();
  });
});
