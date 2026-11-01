import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { changePassword } from "@/lib/api";
import { setTokens } from "@/lib/auth";

import StartingPasswordScreen from "./StartingPasswordScreen";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  changePassword: vi.fn(),
}));

function fill(current: string, next: string, again = next) {
  fireEvent.change(screen.getByLabelText("Password you signed in with"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("New password again"), { target: { value: again } });
}

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(changePassword).mockReset();
});

describe("StartingPasswordScreen", () => {
  it("changes the password and hands over the new pair", async () => {
    vi.mocked(changePassword).mockResolvedValue({ access: "new-access", refresh: "new-refresh" });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<StartingPasswordScreen username="karim" onChanged={onChanged} onSignOut={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Choose your own password" })).toBeInTheDocument();
    fill("Set-By-Sales-1", "Mine-Only-2026");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    });

    expect(changePassword).toHaveBeenCalledWith(
      { current_password: "Set-By-Sales-1", new_password: "Mine-Only-2026", new_password_confirm: "Mine-Only-2026" },
      "access"
    );
    expect(onChanged).toHaveBeenCalledWith({ access: "new-access", refresh: "new-refresh" });
  });

  it("checks the two new passwords match before asking the server", async () => {
    render(<StartingPasswordScreen username="karim" onChanged={vi.fn()} onSignOut={vi.fn()} />);
    fill("Set-By-Sales-1", "Mine-Only-2026", "Mine-Only-2027");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("shows the server's reason and lets the person sign out", async () => {
    vi.mocked(changePassword).mockRejectedValue(new Error("Choose a password different from your current one."));
    const onSignOut = vi.fn();
    render(<StartingPasswordScreen username="karim" onChanged={vi.fn()} onSignOut={onSignOut} />);
    fill("Set-By-Sales-1", "Set-By-Sales-1");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("different from your current one");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalled();
  });
});
