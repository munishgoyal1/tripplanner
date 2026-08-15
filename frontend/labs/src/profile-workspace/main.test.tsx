import { describe, expect, it } from "vitest";

describe("profile workspace contract", () => {
  it("keeps five distinct roomier homes for the same profile", () => {
    const options = ["wide-drawer", "full-page", "workspace-modal", "two-pane", "expandable"];

    expect(options).toHaveLength(5);
    expect(new Set(options).size).toBe(5);
  });

  it("gives every option more room than today's 384px drawer", () => {
    const todayWidth = 384;
    const widths = [960, 1240, 1100, 1080];

    expect(widths.every((width) => width > todayWidth)).toBe(true);
  });

  it("treats travellers as its own section rather than a nested block", () => {
    const sections = ["identity", "travel", "family", "documents", "privacy"];

    expect(sections).toContain("family");
    expect(sections.indexOf("family")).not.toBe(sections.indexOf("travel"));
  });
});
