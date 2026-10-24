import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit and component tests (`npm test`). Next.js builds the app; Vitest only
// needs to compile TS/TSX and resolve the same `@/` alias as tsconfig.json.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    unstubGlobals: true,
    // What vi.useFakeTimers() replaces. Vitest's default list also fakes
    // process.hrtime and nextTick, which its own hook timeout relies on: the
    // afterEach after any fake-timer test then fails as "timed out".
    fakeTimers: { toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] },
  },
});
