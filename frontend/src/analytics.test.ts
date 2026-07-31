import { beforeEach, describe, expect, it, vi } from "vitest";
import { enableAnalytics, trackEvent } from "./analytics";

describe("analytics", () => {
  beforeEach(() => {
    document.head.innerHTML = "";
    localStorage.clear();
    window.history.replaceState({}, "", "/?share=sensitive-token");
    delete (window as Window & { dataLayer?: unknown[] }).dataLayer;
    delete (window as Window & { gtag?: (...args: unknown[]) => void }).gtag;
    vi.restoreAllMocks();
  });

  it("does not send events before consent enables analytics", () => {
    trackEvent("planning_started");
    expect((window as Window & { dataLayer?: unknown[] }).dataLayer).toBeUndefined();
  });

  it("records a query-free page view and content-free funnel event", () => {
    enableAnalytics("G-ABC123");
    trackEvent("planning_started", { retry: false });

    const queued = (window as Window & { dataLayer?: unknown[] }).dataLayer;
    const commands = queued?.map((command) => Array.from(command as ArrayLike<unknown>));
    expect(commands).toBeDefined();
    if (!commands) return;
    expect(Object.prototype.toString.call(queued?.[0])).toBe("[object Arguments]");
    expect(commands).toContainEqual([
      "event",
      "page_view",
      expect.objectContaining({ page_location: `${window.location.origin}/` }),
    ]);
    expect(JSON.stringify(commands)).not.toContain("sensitive-token");
    expect(commands).toContainEqual(["event", "planning_started", { retry: false }]);
  });
});