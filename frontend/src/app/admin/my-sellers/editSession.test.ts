import { describe, expect, it } from "vitest";
import { changedFields, cleanCode, isSessionRequired, liveState, phoneList, timeLeft } from "./editSession";

const NOW = Date.parse("2026-11-02T08:00:00Z");
const later = (seconds: number) => new Date(NOW + seconds * 1000).toISOString();

describe("liveState", () => {
  it("keeps an open session open until its end", () => {
    const session = { state: "open" as const, expires_at: later(90), code_expires_at: null, attempts_left: null };
    expect(liveState(session, NOW)).toBe("open");
    expect(liveState(session, NOW + 91_000)).toBe("ended");
  });

  it("lets a waiting code run out", () => {
    const session = { state: "waiting" as const, expires_at: null, code_expires_at: later(30), attempts_left: 5 };
    expect(liveState(session, NOW)).toBe("waiting");
    expect(liveState(session, NOW + 31_000)).toBe("ended");
  });

  it("reads no session as none", () => {
    expect(liveState(null, NOW)).toBe("none");
  });
});

describe("timeLeft", () => {
  it("counts down in minutes and seconds", () => {
    expect(timeLeft(later(725), NOW)).toBe("12:05");
    expect(timeLeft(later(-5), NOW)).toBe("0:00");
  });
});

describe("cleanCode", () => {
  it("takes six digits, spaces allowed", () => {
    expect(cleanCode(" 123 456 ")).toBe("123456");
    expect(cleanCode("12345")).toBeNull();
    expect(cleanCode("12a456")).toBeNull();
  });
});

describe("changedFields", () => {
  it("keeps only what changed", () => {
    expect(changedFields({ name: "A", phone: "1", tags: ["x"] }, { name: "B", phone: "1", tags: ["x"] })).toEqual({
      name: "B",
    });
  });
});

describe("phoneList", () => {
  it("splits on commas and lines", () => {
    expect(phoneList("01711111111, 01822222222\n 01933333333 ,")).toEqual([
      "01711111111",
      "01822222222",
      "01933333333",
    ]);
  });
});

describe("isSessionRequired", () => {
  it("spots the backend's code", () => {
    expect(isSessionRequired({ code: "edit_session_required" })).toBe(true);
    expect(isSessionRequired({ detail: "x" })).toBe(false);
    expect(isSessionRequired(undefined)).toBe(false);
  });
});
