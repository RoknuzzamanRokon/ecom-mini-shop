import { describe, expect, it, vi } from "vitest";

import { CartApiError, addToCartApi, customerRequest, extractApiError } from "./api";
import { getAuthToken, setTokens } from "./auth";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("extractApiError", () => {
  it.each([
    ["DRF's detail", { detail: "Not found." }, "Not found."],
    ["our views' error string", { error: "Order cannot be cancelled." }, "Order cannot be cancelled."],
    ["a message", { message: "Try later." }, "Try later."],
    ["detail before error", { error: "second", detail: "first" }, "first"],
    ["an error holding field errors", { error: { quantity: ["Too many."] } }, "Quantity: Too many."],
    ["a serializer field", { email: ["Enter a valid email address."] }, "Email: Enter a valid email address."],
    ["an _id field, named without the suffix", { product_id: ["Not for sale."] }, "Product: Not for sale."],
    ["a snake_case field", { date_of_birth: ["Too early."] }, "Date of birth: Too early."],
    ["non_field_errors, unlabelled", { non_field_errors: ["Passwords differ."] }, "Passwords differ."],
    ["every message of a list", { password: ["Too short.", "Too common."] }, "Password: Too short. Too common."],
    ["a bare list", ["One.", "Two."], "One. Two."],
    ["a plain string", "  Server says no.  ", "Server says no."],
  ])("reads %s", (_label, body, expected) => {
    expect(extractApiError(body, "fallback")).toBe(expected);
  });

  it.each([
    ["an empty object", {}],
    ["an empty list", []],
    ["a blank string", "   "],
    ["null", null],
    ["a number", 500],
    ["empty field lists", { email: [] }],
  ])("falls back for %s", (_label, body) => {
    expect(extractApiError(body, "Something went wrong")).toBe("Something went wrong");
  });

  it("skips empty fields and never shows raw JSON", () => {
    const message = extractApiError({ detail: "", name: [], stock: [{ quantity: ["Must be 0 or more."] }] }, "x");
    expect(message).toBe("Stock: Quantity: Must be 0 or more.");
    expect(message).not.toMatch(/[{}[\]"]/);
  });
});

describe("customerRequest", () => {
  it("refreshes once on a 401 and retries with the new token", async () => {
    setTokens("expired", "refresh-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Token expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access: "fresh", refresh: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await customerRequest("/api/cart/", "expired");

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
    expect(getAuthToken()).toBe("fresh");
  });

  it("hands back a second 401 as-is, with no third request", async () => {
    setTokens("expired", "refresh-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(jsonResponse({ access: "fresh", refresh: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse({}, 401));
    vi.stubGlobal("fetch", fetchMock);

    const res = await customerRequest("/api/cart/", "expired");

    expect(res.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not refresh for a request sent without a token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 401));
    vi.stubGlobal("fetch", fetchMock);

    const res = await customerRequest("/api/orders/MS-1/");

    expect(res.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("cart request errors", () => {
  it("carry the HTTP status and the server's reason", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ quantity: ["Only 2 left in stock."] }, 400)));

    const error = await addToCartApi(7, 5, "token").catch((err: unknown) => err);

    expect(error).toBeInstanceOf(CartApiError);
    expect(error).toMatchObject({ status: 400, message: "Only 2 left in stock." });
  });

  it("fall back to a generic message when the body has none", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })));

    await expect(addToCartApi(7, 1, "token")).rejects.toMatchObject({
      status: 502,
      message: "Failed to add item to cart",
    });
  });
});
