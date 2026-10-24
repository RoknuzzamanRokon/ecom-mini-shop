import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setTokens } from "@/lib/auth";
import type { Review } from "@/lib/types";

import ReviewSection, { type ReviewAdapter } from "./ReviewSection";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { id: 3 }, isAuthenticated: true }),
}));

const MINE: Review = {
  id: 70,
  user_id: 3,
  reviewer_name: "Nadia",
  rating: 4,
  comment: "Bright and sturdy.",
  is_verified_purchase: true,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};

function adapter(): ReviewAdapter {
  return {
    list: vi.fn().mockResolvedValue({ count: 1, next: null, previous: null, results: [MINE] }),
    getMine: vi.fn().mockResolvedValue(MINE),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  };
}

async function renderWith(reviews: ReviewAdapter) {
  render(<ReviewSection adapter={reviews} loginNext="/product/lamp" commentPlaceholder="..." />);
  await screen.findByText("Your review");
}

beforeEach(() => {
  setTokens("access", "refresh");
});

describe("ReviewSection: deleting your review (BUG-091)", () => {
  it("asks first, and deletes only once confirmed", async () => {
    const reviews = adapter();
    vi.mocked(reviews.remove).mockResolvedValue();
    await renderWith(reviews);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const question = screen.getByRole("group", { name: "Delete your review?" });
    expect(reviews.remove).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    await act(async () => {
      fireEvent.click(question.querySelector("button")!);
    });
    expect(reviews.remove).toHaveBeenCalledWith(70, "access");
  });

  it("keeps the review when cancelled", async () => {
    const reviews = adapter();
    await renderWith(reviews);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("group", { name: "Delete your review?" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(reviews.remove).not.toHaveBeenCalled();
  });

  it("shows why a delete failed, next to the review", async () => {
    const reviews = adapter();
    vi.mocked(reviews.remove).mockRejectedValue(new Error("You can't delete a review under moderation."));
    await renderWith(reviews);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("group", { name: "Delete your review?" }).querySelector("button")!);
    });

    expect(screen.getByRole("alert")).toHaveTextContent("You can't delete a review under moderation.");
    // The review is still yours, with the question open to try again or cancel.
    expect(screen.getByText("Your review")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Delete your review?" })).toBeInTheDocument();
  });
});
