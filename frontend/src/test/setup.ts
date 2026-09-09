import { afterEach } from "vitest";

// Most test files run under the "node" environment (see vitest.config.ts) and
// have no window/document at all. Only the jsdom-environment files (component
// tests) need the DOM-specific setup below.
if (typeof window !== "undefined") {
	await import("@testing-library/jest-dom/vitest");
	const { cleanup } = await import("@testing-library/react");
	afterEach(cleanup);

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
