import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileProvider } from "@/context/ProfileContext";
import { getCustomerProfile, updateCustomerProfile, uploadAvatar } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { CustomerProfile } from "@/lib/types";

import ProfileSettingsPage from "./page";

vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getCustomerProfile: vi.fn(),
  updateCustomerProfile: vi.fn(),
  uploadAvatar: vi.fn(),
}));

const PROFILE: CustomerProfile = {
  id: 11,
  user_id: 3,
  username: "nadia",
  email: "nadia@example.com",
  first_name: "Nadia",
  last_name: "Islam",
  display_name: "Nadia I.",
  phone: "01711111111",
  avatar: null,
  date_of_birth: "1994-02-03",
  gender: "FEMALE",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  return render(
    <ProfileProvider>
      <ProfileSettingsPage />
    </ProfileProvider>
  );
}

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const saveButton = () => screen.getByRole("button", { name: /Save Changes/ });

beforeEach(() => {
  setTokens("access", "refresh");
  vi.mocked(getCustomerProfile).mockReset();
  vi.mocked(updateCustomerProfile).mockReset();
  vi.mocked(uploadAvatar).mockReset();
});

describe("Profile settings (BUG-086)", () => {
  it("keeps the form locked, with a retry, while the profile could not be loaded", async () => {
    vi.mocked(getCustomerProfile).mockRejectedValueOnce(new Error("Service unavailable."));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("We could not load your details");
    expect(field("First Name")).toBeDisabled();
    expect(field("First Name")).toHaveValue("");
    expect(saveButton()).toBeDisabled();
    expect(screen.getByRole("button", { name: /Change Photo/ })).toBeDisabled();

    vi.mocked(getCustomerProfile).mockResolvedValueOnce(PROFILE);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    });

    expect(field("First Name")).toHaveValue("Nadia");
    expect(field("First Name")).toBeEnabled();
    expect(saveButton()).toBeEnabled();
    expect(updateCustomerProfile).not.toHaveBeenCalled();
  });

  it("sends only the fields that changed", async () => {
    vi.mocked(getCustomerProfile).mockResolvedValue(PROFILE);
    vi.mocked(updateCustomerProfile).mockResolvedValue({ ...PROFILE, phone: "01999999999" });
    renderPage();
    await screen.findByDisplayValue("Nadia");

    fireEvent.change(field("Phone"), { target: { value: "01999999999" } });
    await act(async () => {
      fireEvent.click(saveButton());
    });

    expect(updateCustomerProfile).toHaveBeenCalledWith({ phone: "01999999999" }, "access");
    expect(screen.getByText("Profile details saved.")).toBeInTheDocument();
  });

  it("sends null for a cleared date of birth, and nothing at all when nothing changed", async () => {
    vi.mocked(getCustomerProfile).mockResolvedValue(PROFILE);
    vi.mocked(updateCustomerProfile).mockResolvedValue({ ...PROFILE, date_of_birth: null });
    renderPage();
    await screen.findByDisplayValue("Nadia");

    await act(async () => {
      fireEvent.click(saveButton());
    });
    expect(updateCustomerProfile).not.toHaveBeenCalled();
    expect(screen.getByText("No changes to save.")).toBeInTheDocument();

    fireEvent.change(field("Date of Birth"), { target: { value: "" } });
    await act(async () => {
      fireEvent.click(saveButton());
    });
    expect(updateCustomerProfile).toHaveBeenCalledWith({ date_of_birth: null }, "access");
  });

  it("keeps unsaved edits when a new photo is uploaded", async () => {
    vi.mocked(getCustomerProfile).mockResolvedValue(PROFILE);
    vi.mocked(uploadAvatar).mockResolvedValue({ ...PROFILE, avatar: "/media/avatars/nadia.jpg" });
    const { container } = renderPage();
    await screen.findByDisplayValue("Nadia");

    fireEvent.change(field("Display Name"), { target: { value: "Nadia from Dhaka" } });
    const photo = new File(["x"], "me.png", { type: "image/png" });
    await act(async () => {
      fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [photo] } });
    });

    expect(screen.getByText("Photo updated.")).toBeInTheDocument();
    expect(field("Display Name")).toHaveValue("Nadia from Dhaka");
  });
});
