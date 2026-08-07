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

  it("keeps an outcome on screen until something newer replaces it", () => {
    vi.useFakeTimers();
    notify({ id: "done", tone: "success", message: "Switched to Rome." });
    notify({ id: "failed", tone: "error", message: "Could not remove the place." });
    vi.advanceTimersByTime(60_000);
    expect(readNotice()?.message).toBe("Could not remove the place.");

    dismissNotice("failed");
    expect(readNotice()?.message).toBe("Switched to Rome.");
  });

  it("carries a detail line alongside the headline", () => {
    notify({
      id: "added",
      tone: "success",
      message: "Added Kaanch Mandir",
      detail: "Day 2 was packed, so I moved Lal Bagh Palace to Day 3.",
    });
    expect(readNotice()?.detail).toBe("Day 2 was packed, so I moved Lal Bagh Palace to Day 3.");
  });
});
