import { afterEach, describe, expect, it, vi } from "vitest";

import { updateMyOnboardedProduct } from "./admin-api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("updateMyOnboardedProduct", () => {
  it("sends JSON without a photo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 21 }));
    vi.stubGlobal("fetch", fetchMock);

    await updateMyOnboardedProduct("access", 21, { stock: 12, expected_stock: 10 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/onboarding\/products\/21\/$/);
    expect(init.method).toBe("PATCH");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ stock: 12, expected_stock: 10 });
  });

  it("sends multipart with a photo, an empty value standing for null", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 21 }));
    vi.stubGlobal("fetch", fetchMock);
    const photo = new File(["png"], "shelf.png", { type: "image/png" });

    await updateMyOnboardedProduct("access", 21, { image: photo, old_price: null, is_active: false });

    const init = fetchMock.mock.calls[0][1];
    expect(init.method).toBe("PATCH");
    // The browser writes the multipart Content-Type with its boundary.
    expect(init.headers["Content-Type"]).toBeUndefined();
    const body = init.body as FormData;
    expect(body.get("image")).toBeInstanceOf(File);
    expect((body.get("image") as File).name).toBe("shelf.png");
    expect(body.get("old_price")).toBe("");
    expect(body.get("is_active")).toBe("false");
  });
});
