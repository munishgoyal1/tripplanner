import { describe, expect, it } from "vitest";

import { rankedOptions } from "../shared/OptionContrast";
import { allLabs, LAST_ASSIGNED_LAB_NUMBER } from "../shared/labRecords";
import { options } from "./options";

describe("trip feedback contract", () => {
  it("offers five distinct homes for one feedback control", () => {
    expect(options).toHaveLength(5);
    expect(new Set(options.map((option) => option.id)).size).toBe(5);
  });

  it("letters and orders the cards exactly as the contrast table scores them", () => {
    const ranked = rankedOptions("trip-feedback");

    expect(options.map((option) => option.label)).toEqual(ranked.map((option) => option.label));
    expect(options[0].label.startsWith("A · ")).toBe(true);
    expect(options[0].name).toBe("Toolbar rating pill");
  });

  it("states a resting footprint and a reach for every option", () => {
    // The whole argument is placement cost, so an option that does not say what
    // it occupies while unused cannot be compared with the others.
    for (const option of options) {
      expect(option.resting.trim().length).toBeGreaterThan(0);
      expect(option.reach.trim().length).toBeGreaterThan(0);
    }
  });

  it("keeps both always-reachable options reachable from every pane", () => {
    const everywhere = options.filter((option) => option.reach === "Every pane");

    expect(everywhere.map((option) => option.id).sort()).toEqual(["floating-tab", "toolbar-pill"]);
  });

  it("registers Lab 29 as the newest allocated number", () => {
    const lab = allLabs.find((candidate) => candidate.id === "trip-feedback");

    expect(lab?.labNumber).toBe(29);
    expect(LAST_ASSIGNED_LAB_NUMBER).toBe(29);
    expect(lab?.href).toBe("./lab-29-trip-feedback.html");
  });
});
