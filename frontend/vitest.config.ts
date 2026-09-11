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
    // Observed a real (non-hung) integration test take ~16s under full
    // concurrent load from other lanes, so the budget has headroom above that.
    testTimeout: 20_000,
    pool: "forks",
    // Unbounded workers (default: one per logical CPU, 12 here) spawn all at
    // once and produced "[vitest-pool-runner]: Timeout waiting for worker
    // to respond" when several worktrees validate concurrently (full 2-way
    // sync, sandbox promotion) plus AV scanning of a freshly npm-installed
    // temp worktree. A fixed cap avoids that oversubscription (same
    // rationale as pytest -n 2 in full-2way-sync.ps1) while still running
    // files in parallel.
    maxWorkers: 4,
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
