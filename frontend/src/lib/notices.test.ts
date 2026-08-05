import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearNotices, dismissNotice, notify, readNotice } from "./notices";

describe("notice channel", () => {
  beforeEach(() => {
    clearNotices();
    vi.useRealTimers();
  });

  it("shows the most urgent notice and falls back when it is dismissed", () => {
    notify({ id: "a", tone: "progress", message: "Switching to Rome…" });
    notify({ id: "b", tone: "error", message: "Could not add the place." });
    expect(readNotice()?.message).toBe("Could not add the place.");

    dismissNotice("b");
    expect(readNotice()?.message).toBe("Switching to Rome…");
  });

  it("lets an operation replace its own notice with the outcome", () => {
    notify({ id: "trip-switch", tone: "progress", message: "Switching to Rome…" });
    notify({ id: "trip-switch", tone: "success", message: "Switched to Rome." });
    expect(readNotice()?.message).toBe("Switched to Rome.");
  });

  it("expires an outcome but keeps a failure until it is dismissed", () => {
    vi.useFakeTimers();
    notify({ id: "done", tone: "success", message: "Switched to Rome." });
    notify({ id: "failed", tone: "error", message: "Could not remove the place." });
    vi.advanceTimersByTime(10_000);
    expect(readNotice()?.message).toBe("Could not remove the place.");

    dismissNotice("failed");
    expect(readNotice()).toBeNull();
  });
});
