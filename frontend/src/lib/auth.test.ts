import { describe, expect, it, vi } from "vitest";

import {
  AuthUnavailableError,
  getAuthToken,
  getRefreshToken,
  onAuthCleared,
  refreshTokenOnce,
  safeNextPath,
  setTokens,
} from "./auth";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** A fetch whose responses the test releases by hand, so calls can overlap. */
function deferredFetch() {
  const pending: ((response: Response) => void)[] = [];
  const fetchMock = vi.fn<typeof fetch>(() => new Promise((resolve) => pending.push(resolve)));
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, respond: (response: Response) => pending.shift()!(response) };
}

describe("safeNextPath", () => {
  it.each([
    ["/profile", "/profile"],
    ["/profile/orders?page=2#latest", "/profile/orders?page=2#latest"],
    ["/checkout/../cart", "/cart"],
  ])("keeps the on-site path %s", (raw, expected) => {
    expect(safeNextPath(raw)).toBe(expected);
  });

  it.each([
    ["https://evil.example/login"],
    ["//evil.example"],
    ["/\\evil.example"],
    ["/\t/evil.example"],
    ["/\n/evil.example"],
    ["javascript:alert(1)"],
    ["profile"],
    [""],
    [null],
    [undefined],
  ])("falls back for %j", (raw) => {
    expect(safeNextPath(raw)).toBe("/");
    expect(safeNextPath(raw, "/login")).toBe("/login");
  });
});

describe("refreshTokenOnce", () => {
  it("sends one refresh for a burst of callers and gives them all the new token", async () => {
    setTokens("old-access", "old-refresh");
    const { fetchMock, respond } = deferredFetch();

    const callers = [refreshTokenOnce(), refreshTokenOnce(), refreshTokenOnce()];
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    respond(jsonResponse({ access: "new-access", refresh: "new-refresh" }));

    await expect(Promise.all(callers)).resolves.toEqual(["new-access", "new-access", "new-access"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/auth\/token\/refresh\/$/);
    expect(getAuthToken()).toBe("new-access");
    expect(getRefreshToken()).toBe("new-refresh");
  });

  it("starts a fresh refresh once the previous one has settled", async () => {
    setTokens("a1", "r1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ access: "a2", refresh: "r2" }))
      .mockResolvedValueOnce(jsonResponse({ access: "a3", refresh: "r3" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(refreshTokenOnce()).resolves.toBe("a2");
    await expect(refreshTokenOnce()).resolves.toBe("a3");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ refresh: "r2" });
  });

  it("clears the session and tells subscribers once when the server refuses the refresh token", async () => {
    setTokens("access", "blacklisted");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Token is blacklisted" }, 401)));
    const cleared = vi.fn();
    const unsubscribe = onAuthCleared(cleared);

    const results = await Promise.all([refreshTokenOnce(), refreshTokenOnce()]);
    unsubscribe();

    expect(results).toEqual([null, null]);
    expect(cleared).toHaveBeenCalledTimes(1);
    expect(getAuthToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it.each([
    ["a 503", () => vi.fn().mockResolvedValue(jsonResponse({}, 503))],
    ["a network failure", () => vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))],
  ])("keeps the tokens and rejects with AuthUnavailableError after %s", async (_label, makeFetch) => {
    setTokens("access", "refresh");
    vi.stubGlobal("fetch", makeFetch());
    const cleared = vi.fn();
    const unsubscribe = onAuthCleared(cleared);

    await expect(refreshTokenOnce()).rejects.toBeInstanceOf(AuthUnavailableError);
    unsubscribe();

    expect(cleared).not.toHaveBeenCalled();
    expect(getAuthToken()).toBe("access");
    expect(getRefreshToken()).toBe("refresh");
  });

  it("treats a missing refresh token as a signed-out session without a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(refreshTokenOnce()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
