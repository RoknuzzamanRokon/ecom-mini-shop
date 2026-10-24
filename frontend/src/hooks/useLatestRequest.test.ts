import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { useLatestRequest } from "./useLatestRequest";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

/** A list loader the way the Console pages use the hook. */
function useLoader() {
  const beginRequest = useLatestRequest();
  const [rows, setRows] = useState<string[]>([]);
  const load = async (request: Promise<string[]>) => {
    const isLatest = beginRequest();
    const data = await request;
    if (!isLatest()) return;
    setRows(data);
  };
  return { rows, load };
}

describe("useLatestRequest", () => {
  it("keeps the newer request's result when an older one answers last", async () => {
    const { result } = renderHook(useLoader);
    const older = deferred<string[]>();
    const newer = deferred<string[]>();

    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = result.current.load(older.promise);
      second = result.current.load(newer.promise);
    });
    await act(async () => {
      newer.resolve(["new filter"]);
      await second;
    });
    await act(async () => {
      older.resolve(["old filter"]);
      await first;
    });

    expect(result.current.rows).toEqual(["new filter"]);
  });

  it("applies requests that finish in order", async () => {
    const { result } = renderHook(useLoader);

    await act(() => result.current.load(Promise.resolve(["page 1"])));
    expect(result.current.rows).toEqual(["page 1"]);
    await act(() => result.current.load(Promise.resolve(["page 2"])));
    expect(result.current.rows).toEqual(["page 2"]);
  });

  it("drops every answer after unmount", () => {
    const { result, unmount } = renderHook(() => useLatestRequest());

    const isLatest = result.current();
    expect(isLatest()).toBe(true);
    unmount();
    expect(isLatest()).toBe(false);
  });

  it("gives the same begin function on every render", () => {
    const { result, rerender } = renderHook(() => useLatestRequest());
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});
