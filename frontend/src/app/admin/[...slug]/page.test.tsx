import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AdminNotFound from "../not-found";
import AdminUnknownPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));

describe("unknown Console addresses (BUG-082)", () => {
  it("are a 404, not a module placeholder", () => {
    expect(() => AdminUnknownPage()).toThrow("NEXT_NOT_FOUND");
  });

  it("show the Console's not-found page, linking back to the overview", () => {
    render(<AdminNotFound />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to Overview" })).toHaveAttribute("href", "/admin");
    expect(screen.queryByText(/Foundation Ready|Awaiting Implementation/)).not.toBeInTheDocument();
  });
});
