import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDebouncedUrlValue } from "./useDebouncedUrlValue";

function setup(initialUrl = "") {
  const commit = vi.fn();
  const view = renderHook(({ url }) => useDebouncedUrlValue(url, commit), { initialProps: { url: initialUrl } });
  return { commit, view, input: () => view.result.current[0], type: (v: string) => act(() => view.result.current[1](v)) };
}

describe("useDebouncedUrlValue", () => {
  it("commits once typing pauses", () => {
    vi.useFakeTimers();
    const { commit, type } = setup();

    type("a");
    act(() => vi.advanceTimersByTime(200));
    type("ab");
    act(() => vi.advanceTimersByTime(349));
    expect(commit).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(commit).toHaveBeenCalledExactlyOnceWith("ab");
  });

  it("keeps keystrokes typed while its own navigation is in flight (BUG-117)", () => {
    vi.useFakeTimers();
    const { commit, view, input, type } = setup();

    type("abc");
    act(() => vi.advanceTimersByTime(350));
    expect(commit).toHaveBeenLastCalledWith("abc");
    // The user types on before the URL update lands.
    type("abcd");
    view.rerender({ url: "abc" });

    expect(input()).toBe("abcd");
    act(() => vi.advanceTimersByTime(350));
    expect(commit).toHaveBeenLastCalledWith("abcd");
  });

  it("follows the URL when it changes from outside", () => {
    vi.useFakeTimers();
    const { commit, view, input, type } = setup("old");

    view.rerender({ url: "from-back-button" });
    expect(input()).toBe("from-back-button");

    // After its own commit has landed, a later outside change still wins.
    type("mine");
    act(() => vi.advanceTimersByTime(350));
    view.rerender({ url: "mine" });
    view.rerender({ url: "" });
    expect(input()).toBe("");
    act(() => vi.advanceTimersByTime(1000));
    expect(commit).toHaveBeenCalledTimes(1);
  });
});
