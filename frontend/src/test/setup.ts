import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  // Vitest runs without globals, so Testing Library cannot register its own
  // cleanup. Every test also starts on real timers and an empty localStorage.
  vi.useRealTimers();
  cleanup();
  localStorage.clear();
});
