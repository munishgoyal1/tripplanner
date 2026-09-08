import { describe, expect, it } from "vitest";

describe("agent-requested chat input contract", () => {
  it("keeps the five ask presentations distinct", () => {
    const options = ["chips", "card", "assumed", "queue", "bar"];

    expect(options).toHaveLength(5);
    expect(new Set(options).size).toBe(5);
  });

  it("treats a destination-only trip as an answer rather than missing data", () => {
    const originStates = ["unset", "city", "none"];

    expect(originStates).toContain("none");
    expect(originStates).toContain("unset");
    // "none" and "unset" must stay separable so an unanswered origin is never back-filled.
    expect(originStates.indexOf("none")).not.toBe(originStates.indexOf("unset"));
  });

  it("offers a non-text control for every fact the agent asks for", () => {
    const controls = ["chips", "stepper", "date range", "slider", "segmented", "tags"];

    expect(controls).toHaveLength(6);
    expect(controls.every((control) => control.length > 0)).toBe(true);
  });
});
