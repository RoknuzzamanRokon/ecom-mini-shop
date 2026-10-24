import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@/test/axe";

import Dialog from "./Dialog";

function Harness({ dismissible = true, onClose = () => {} }: { dismissible?: boolean; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Dialog
        open={open}
        onClose={() => {
          onClose();
          setOpen(false);
        }}
        dismissible={dismissible}
        labelledBy="dialog-title"
      >
        <h2 id="dialog-title">Delete the photo?</h2>
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>
    </>
  );
}

describe("Dialog (BUG-094)", () => {
  it("is a named modal dialog that takes focus and keeps Tab inside", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    const dialog = screen.getByRole("dialog", { name: "Delete the photo?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Last" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Last" })).toHaveFocus();

    expect(await axeViolations()).toEqual([]);
  });

  it("closes on Escape and gives focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("closes on a backdrop click", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    await user.click(document.querySelector('[aria-hidden="true"].absolute')!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open while it may not be dismissed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness dismissible={false} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
