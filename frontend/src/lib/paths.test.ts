import { describe, expect, it, vi } from "vitest";

import { getAdminShopDetail } from "./admin-api";
import { cancelCustomerOrder, getProductDetail } from "./api";
import { pathSegment } from "./paths";

describe("pathSegment (BUG-093)", () => {
  it.each([
    [42, "42"],
    ["ORD-1001", "ORD-1001"],
    ["a/b", "a%2Fb"],
    ["..%2F..%2Fusers", "..%252F..%252Fusers"],
    ["%2E%2E", "%252E%252E"],
    ["x?admin=1#top", "x%3Fadmin%3D1%23top"],
  ])("encodes %j as %j", (value, expected) => {
    expect(pathSegment(value)).toBe(expected);
  });

  it.each(["", ".", ".."])("refuses %j, which the URL parser would drop or climb", (value) => {
    expect(() => pathSegment(value)).toThrow("cannot be used as a path segment");
  });
});

describe("API path builders", () => {
  /** The path the backend routes on: the browser's URL, decoded once by the server. */
  function lastPath(fetchMock: ReturnType<typeof vi.fn>) {
    return decodeURIComponent(new URL(String(fetchMock.mock.lastCall?.[0])).pathname);
  }

  it.each([
    ["Console shop detail", () => getAdminShopDetail("token", "1%2F..%2F..%2Fusers"), "/api/admin/shops/"],
    ["customer order cancel", () => cancelCustomerOrder("..%2Fstaff", "token"), "/api/orders/"],
    ["public product detail", () => getProductDetail("%2E%2E"), "/api/products/"],
  ])("keep a crafted %s value inside its own endpoint", async (_label, call, prefix) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await call().catch(() => undefined);

    const path = lastPath(fetchMock);
    expect(path.startsWith(prefix)).toBe(true);
    expect(path.slice(prefix.length).replace(/\/(cancel\/)?$/, "")).not.toContain("/");
  });
});
