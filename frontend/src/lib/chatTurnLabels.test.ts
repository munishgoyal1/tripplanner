import { describe, expect, it } from "vitest";
import { clockDate, clockLabel } from "./chatTurnLabels";

describe("clockLabel", () => {
  it("renders epoch milliseconds in the viewer's local timezone", () => {
    const ts = Date.UTC(2026, 8, 10, 8, 53, 0);
    expect(clockLabel(ts)).toBe(
      new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
    );
  });

  it("treats unix seconds as seconds, not as 1970 milliseconds", () => {
    const seconds = Math.floor(Date.UTC(2026, 8, 10, 8, 53, 0) / 1000);
    expect(clockDate(seconds).getTime()).toBe(seconds * 1000);
    expect(clockLabel(seconds)).toBe(clockLabel(seconds * 1000));
  });

  it("parses UTC ISO strings into the same local clock as epoch ms", () => {
    const iso = "2026-09-10T08:53:00.000Z";
    const ts = Date.parse(iso);
    expect(clockLabel(iso)).toBe(clockLabel(ts));
  });
});
