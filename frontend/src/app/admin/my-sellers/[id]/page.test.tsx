import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AdminApiError,
  getMyOnboardedProduct,
  getMyOnboardedSeller,
  requestEditCode,
  updateMyOnboardedProduct,
  updateMyOnboardedSeller,
  verifyEditCode,
  type AdminEditSession,
  type AdminMyOnboardedSeller,
  type AdminOnboardedProductDetail,
} from "@/lib/admin-api";
import { setTokens } from "@/lib/auth";
import { setRouteParams } from "@/test/navigation";

import AdminMySellerDetailPage from "./page";

vi.mock("next/navigation", () => import("@/test/navigation"));
vi.mock("next/link", () => import("@/test/next-link"));
vi.mock("next/image", () => import("@/test/next-image"));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { is_superuser: false, permissions: ["sellers.onboard", "onboarding.products.view"] } }),
}));
vi.mock("@/lib/admin-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/admin-api")>()),
  getMyOnboardedSeller: vi.fn(),
  requestEditCode: vi.fn(),
  verifyEditCode: vi.fn(),
  closeEditSession: vi.fn(),
  updateMyOnboardedSeller: vi.fn(),
  updateMyOnboardedShop: vi.fn(),
  getMyOnboardedProduct: vi.fn(),
  updateMyOnboardedProduct: vi.fn(),
}));

const inMinutes = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
const NONE: AdminEditSession = { state: "none", code_expires_at: null, expires_at: null, attempts_left: null };
const WAITING: AdminEditSession = { state: "waiting", code_expires_at: inMinutes(10), expires_at: null, attempts_left: 5 };
const OPEN: AdminEditSession = { state: "open", code_expires_at: null, expires_at: inMinutes(30), attempts_left: null };

function seller(overrides: Partial<AdminMyOnboardedSeller> = {}): AdminMyOnboardedSeller {
  return {
    id: 4,
    business_name: "Corner Store",
    seller_type: "LIMITED_SHOP_OWNER",
    status: "PENDING",
    rejection_reason: "",
    username: "corner_owner",
    phone: "+8801712345678",
    onboarded_by: "sales",
    shop_count: 1,
    product_count: 1,
    starting_points: 200,
    tokens_awarded: 51,
    created_at: "2026-10-30T10:00:00Z",
    business_email: "",
    business_phone: "01811111111",
    tax_id: "",
    description: "",
    email: "",
    first_name: "Karim",
    last_name: "",
    points_balance: 195,
    approved_at: null,
    reversed_at: null,
    points_returned: 0,
    tokens_taken_back: 0,
    can_view_products: true,
    edit_session: NONE,
    shops: [
      {
        id: 9,
        name: "Corner Store Mirpur",
        slug: "corner-store-mirpur",
        status: "PENDING",
        rejection_reason: "",
        phone: "",
        additional_phones: [],
        address: "Mirpur 10",
        description: "",
        latitude: 23.807,
        longitude: 90.368,
        created_at: "2026-10-30T10:05:00Z",
        products: [
          {
            id: 21,
            name: "Rice 5kg",
            slug: "rice-5kg",
            category: "Grocery",
            price: "450.00",
            old_price: null,
            stock: 10,
            status: "SUBMITTED",
            rejection_reason: "",
            image_url: null,
            created_at: "2026-10-30T10:10:00Z",
          },
        ],
      },
    ],
    ...overrides,
  };
}

const PRODUCT: AdminOnboardedProductDetail = {
  ...seller().shops[0].products[0],
  category_id: 3,
  description: "Miniket",
  badge: "",
  is_active: true,
  live_until: null,
  shop_id: 9,
  shop_name: "Corner Store Mirpur",
  seller_id: 4,
  seller_name: "Corner Store",
};

async function openPage() {
  render(<AdminMySellerDetailPage />);
  await act(async () => {});
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  setRouteParams({ id: "4" });
  setTokens("access", "refresh");
  vi.mocked(getMyOnboardedSeller).mockReset().mockResolvedValue(seller());
  vi.mocked(requestEditCode).mockReset().mockResolvedValue(WAITING);
  vi.mocked(verifyEditCode).mockReset().mockResolvedValue(OPEN);
  vi.mocked(updateMyOnboardedSeller).mockReset();
  vi.mocked(getMyOnboardedProduct).mockReset().mockResolvedValue(PRODUCT);
  vi.mocked(updateMyOnboardedProduct).mockReset();
});

describe("My Sellers detail page", () => {
  it("asks the seller for a code, then opens editing", async () => {
    await openPage();
    expect(screen.queryByRole("button", { name: "Edit business details" })).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Send code to seller/ }));
    });
    expect(requestEditCode).toHaveBeenCalledWith("access", 4);
    expect(screen.getByText(/A code was sent to Corner Store's account/)).toBeInTheDocument();

    const input = screen.getByLabelText("Seller's code");
    fireEvent.change(input, { target: { value: "12345" } });
    expect(screen.getByRole("button", { name: "Open editing" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "123 456" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open editing" }));
    });

    expect(verifyEditCode).toHaveBeenCalledWith("access", 4, "123456");
    expect(screen.getByText("Editing is open")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit business details" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Corner Store Mirpur" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Rice 5kg" })).toBeInTheDocument();
  });

  it("shows the server's word on a wrong code", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ edit_session: WAITING }));
    vi.mocked(verifyEditCode).mockRejectedValue(new AdminApiError("Wrong code. 4 tries left.", 400));
    await openPage();

    fireEvent.change(screen.getByLabelText("Seller's code"), { target: { value: "000000" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open editing" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Wrong code. 4 tries left.");
  });

  it("sends only the changed business details", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ edit_session: OPEN }));
    vi.mocked(updateMyOnboardedSeller).mockResolvedValue(seller({ edit_session: OPEN, business_name: "Karim Traders" }));
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Edit business details" }));
    fireEvent.change(dialog().getByLabelText("Business name"), { target: { value: "  Karim Traders " } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save changes" }));
    });

    expect(updateMyOnboardedSeller).toHaveBeenCalledWith("access", 4, { business_name: "Karim Traders" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Karim Traders");
  });

  it("sends a new stock with the figure it was edited from", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ edit_session: OPEN }));
    vi.mocked(updateMyOnboardedProduct).mockResolvedValue({ ...PRODUCT, stock: 12 });
    await openPage();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Edit Rice 5kg" }));
    });
    expect(getMyOnboardedProduct).toHaveBeenCalledWith("access", 21);
    fireEvent.change(dialog().getByLabelText("Stock"), { target: { value: "12" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save changes" }));
    });

    expect(updateMyOnboardedProduct).toHaveBeenCalledWith("access", 21, { stock: 12, expected_stock: 10 });
    expect(screen.getByText("৳450.00 · 12 in stock")).toBeInTheDocument();
  });

  it("replaces the product photo, and refuses a format the server would", async () => {
    // jsdom has no object URLs.
    URL.createObjectURL = vi.fn(() => "blob:shelf");
    URL.revokeObjectURL = vi.fn();
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ edit_session: OPEN }));
    vi.mocked(updateMyOnboardedProduct).mockResolvedValue({ ...PRODUCT, image_url: "/media/products/shelf.png" });
    await openPage();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Edit Rice 5kg" }));
    });
    const input = dialog().getByLabelText("Photo");
    fireEvent.change(input, { target: { files: [new File(["gif"], "shelf.gif", { type: "image/gif" })] } });
    expect(dialog().getByRole("alert")).toHaveTextContent("Choose a JPEG, PNG or WebP image.");

    const photo = new File(["png"], "shelf.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [photo] } });
    expect(dialog().getByRole("img", { name: "The new photo" })).toHaveAttribute("src", "blob:shelf");
    expect(dialog().getByText("shelf.png")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save changes" }));
    });

    expect(updateMyOnboardedProduct).toHaveBeenCalledWith("access", 21, { image: photo });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:shelf");
  });

  it("closes editing when the server says the session is over", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ edit_session: OPEN }));
    vi.mocked(updateMyOnboardedSeller).mockRejectedValue(
      new AdminApiError("Editing needs the seller's consent.", 403, { code: "edit_session_required" })
    );
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: "Edit business details" }));
    fireEvent.change(dialog().getByLabelText("Tax ID"), { target: { value: "TIN-1" } });
    await act(async () => {
      fireEvent.click(dialog().getByRole("button", { name: "Save changes" }));
    });
    expect(dialog().getByRole("alert")).toHaveTextContent("Editing needs the seller's consent.");
    fireEvent.click(dialog().getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Edit business details" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send code to seller/ })).toBeInTheDocument();
  });

  it("hides products when the permission is turned off", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(
      seller({ can_view_products: false, shops: [{ ...seller().shops[0], products: [] }] })
    );
    await openPage();
    expect(screen.getByRole("note")).toHaveTextContent("You cannot see products");
    expect(screen.queryByText("Rice 5kg")).not.toBeInTheDocument();
  });

  it("offers no editing for a rejected seller", async () => {
    vi.mocked(getMyOnboardedSeller).mockResolvedValue(seller({ status: "REJECTED", rejection_reason: "Closed" }));
    await openPage();
    expect(screen.getByText("Corner Store can no longer be edited here.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Send code to seller/ })).not.toBeInTheDocument();
  });
});
