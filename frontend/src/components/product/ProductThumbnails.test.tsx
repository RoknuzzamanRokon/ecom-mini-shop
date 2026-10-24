import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@/test/axe";

import ProductThumbnails from "./ProductThumbnails";

vi.mock("next/image", () => import("@/test/next-image"));

const IMAGES = ["/media/a.jpg", "/media/b.jpg", "/media/c.jpg"];

describe("ProductThumbnails (BUG-094)", () => {
  it("names each thumbnail and marks the one on screen", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ProductThumbnails images={IMAGES} selected="/media/b.jpg" onSelect={onSelect} />);

    expect(screen.getByRole("button", { name: "Show image 1 of 3" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Show image 2 of 3" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Show image 3 of 3" }));
    expect(onSelect).toHaveBeenCalledWith("/media/c.jpg");
    expect(await axeViolations()).toEqual([]);
  });

  it("shows nothing for a single image", () => {
    const { container } = render(<ProductThumbnails images={["/media/a.jpg"]} selected="/media/a.jpg" onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
