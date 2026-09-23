// @vitest-environment node
import { describe, expect, it } from "vitest";

import { rankedOptions } from "../shared/OptionContrast";
import { allLabs, LAST_ASSIGNED_LAB_NUMBER } from "../shared/labRecords";
import { days, gaps, improvements } from "./fixture";
import { options } from "./options";

describe("honest gaps contract", () => {
  it("offers four distinct homes for the same open decisions, ordered by score", () => {
    const ranked = rankedOptions("honest-gaps");
    expect(options).toHaveLength(4);
    expect(options.map((option) => option.label)).toEqual(ranked.map((option) => option.label));
    expect(options[0].name).toBe("Decision inbox");
  });

  it("links every placeholder stop to a gap and every gap to at least one stop", () => {
    const linked = new Set(days.flatMap((day) => day.stops.map((stop) => stop.gap).filter(Boolean)));
    expect([...linked].sort()).toEqual(gaps.map((gap) => gap.id).sort());
    for (const stop of days.flatMap((day) => day.stops)) {
      if (/\(TBD\)/.test(stop.name)) expect(stop.gap).toBeTruthy();
    }
  });

  it("gives every gap at least two ways forward", () => {
    for (const gap of gaps) expect(gap.suggestions.length).toBeGreaterThanOrEqual(2);
  });

  it("ranks the follow-up improvements without gaps in the order", () => {
    expect(improvements.map((item) => item.rank)).toEqual(improvements.map((_, index) => index + 1));
  });

  it("registers Lab 32 as the latest allocation", () => {
    const lab = allLabs.find((candidate) => candidate.id === "honest-gaps");
    expect(lab?.labNumber).toBe(32);
    expect(LAST_ASSIGNED_LAB_NUMBER).toBeGreaterThanOrEqual(32);
    expect(lab?.href).toBe("./lab-32-honest-gaps.html");
  });
});
