import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// jsdom setup is expensive (tens of seconds per file on this machine) and
// most test files are pure logic with no DOM. Split into two projects so
// only files that actually render components pay for it; everything else
// runs under the cheap "node" environment. `environmentMatchGlobs` did this
// in older Vitest but was removed in v4 in favor of `projects`.
const domOnlyTests = [
  "**/*.test.tsx",
  "src/components/map/overlaySync.test.ts",
  "src/components/MapPanel.test.ts",
  "src/analytics.test.ts",
  "src/api.test.ts",
  "src/turnMetadata.test.ts",
  "src/auth/authSession.test.ts",
  "src/debug/inspectSession.test.ts",
];

export default defineConfig({
  plugins: [react()],
  test: {
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
    restoreMocks: true,
    // The default 5s per-test budget is tight for a machine under real load
    // (a full `vitest run` alongside tsc/build during sandbox promotion, or
    // several test workers competing for CPU). A hung test still fails; this
    // just stops ordinary contention from reading as a real regression.
    testTimeout: 15_000,
    projects: [
      {
        extends: true,
        test: {
          name: "dom",
          environment: "jsdom",
          include: domOnlyTests,
        },
      },
      {
        extends: true,
        test: {
          name: "node",
          environment: "node",
          include: ["**/*.test.ts"],
          exclude: [...domOnlyTests, "e2e/**", "node_modules/**"],
        },
      },
    ],
  },
});
