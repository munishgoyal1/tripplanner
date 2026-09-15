import { afterEach } from "vitest";

// Most test files run under the "node" environment (see vitest.config.ts) and
// have no window/document at all. Only the jsdom-environment files (component
// tests) need the DOM-specific setup below.
if (typeof window !== "undefined") {
	await import("@testing-library/jest-dom/vitest");
	const { cleanup, configure } = await import("@testing-library/react");
	afterEach(cleanup);
	// findBy*/waitFor budget. Testing Library's 1s default is not a product latency
	// requirement, and it sits below what a full <App /> costs here with nothing
	// else running: measured 2026-09-15, the first render of a file took 1.4-2.4s
	// to show its day heading and the first accessible-name query another 0.7-2.7s
	// (30ms once warm). App.workspace.integration.test.tsx failed that way alone,
	// and at 2 workers under load so did Root and BookingPage tests. A missing
	// element still fails, after 5s instead of 1s; testTimeout (20s) stays the
	// per-test ceiling for the same contention reason.
	configure({ asyncUtilTimeout: 5_000 });

	const values = new Map<string, string>();
	Object.defineProperty(window, "localStorage", {
		configurable: true,
		value: {
			getItem: (key: string) => values.get(key) ?? null,
			setItem: (key: string, value: string) => values.set(key, String(value)),
			removeItem: (key: string) => values.delete(key),
			clear: () => values.clear(),
			key: (index: number) => Array.from(values.keys())[index] ?? null,
			get length() {
				return values.size;
			},
		},
	});
}
